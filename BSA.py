from functools import lru_cache
import numpy as np
import planetary_computer
import rasterio
from pystac_client import Client
from rasterio.enums import Resampling
from rasterio.warp import transform, transform_bounds
from rasterio.windows import from_bounds

EARTH_HOST = ".".join(["planetarycomputer", "microsoft", "com"])
MARS_HOST = ".".join(["planetarymaps", "usgs", "gov"])
MOON_HOST = ".".join(["pds", "lroc", "im-ldi", "com"])

LIVE_DATASETS = {
    "earth": {
        "portal": "Google Earth Web",
        "stac_url": "/".join(["https:/", EARTH_HOST, "api", "stac", "v1"]),
        "collection": "landsat-c2-l2",
        "scale": 0.0000275,
        "offset": -0.2,
    },
    "mars": {
        "portal": "NASA Mars Trek",
        "url": "/".join(["", "vsicurl", "https:/", MARS_HOST, "mosaic", "Mars_MGS_TES_Albedo_mosaic_global_7410m.tif"]),
        "radius_m": 3396190.0,
    },
    "moon": {
        "portal": "NASA Moon Trek",
        "radius_m": 1737400.0,
    },
}

TILE_KM = 30
GRID_SIZE = 128
_RASTER_CACHE = {}


def _get_cached_dataset(url: str):
    src = _RASTER_CACHE.get(url)
    if src is None or src.closed:
        src = rasterio.open(url)
        _RASTER_CACHE[url] = src
    return src


def get_moon_tile_url(lat, lon):
    lon_360 = (lon + 360.0 if lon < 0 else lon) % 360.0
    if lat >= 60.0:
        filename = "WAC_EMP_643NM_P900N0000_152P.IMG"
    elif lat <= -60.0:
        filename = "WAC_EMP_643NM_P900S0000_152P.IMG"
    else:
        hemi = "N" if lat >= 0.0 else "S"
        quad_idx = min(int(lon_360 // 90), 3)
        quad_centers = ["0450", "1350", "2250", "3150"]
        filename = f"WAC_EMP_643NM_E300{hemi}{quad_centers[quad_idx]}_152P.IMG"
    vsicurl_url = "/".join(["", "vsicurl", "https:/", MOON_HOST, "data", "LRO-L-LROC-5-RDR-V1.0", "LROLRC_2001", "DATA", "MDR", "WAC_EMP", filename])
    return vsicurl_url, filename


@lru_cache(maxsize=128)
def get_earth_broadband_albedo(lat, lon):
    cfg = LIVE_DATASETS["earth"]
    catalog = Client.open(cfg["stac_url"], modifier=planetary_computer.sign_inplace)
    delta = 0.05
    bbox = [lon - delta, lat - delta, lon + delta, lat + delta]
    search = catalog.search(
        collections=[cfg["collection"]],
        bbox=bbox,
        datetime="2024-01-01/2026-11-14",
        query={"eo:cloud_cover": {"lt": 10}, "platform": {"in": ["landsat-8", "landsat-9"]}},
    )
    scene = next(search.items(), None)
    if scene is None:
        raise ValueError("No cloud-free Landsat scenes found for these Earth coordinates.")

    def read_band(band_name):
        with rasterio.open(scene.assets[band_name].href) as src:
            left, bottom, right, top = transform_bounds("EPSG:4326", src.crs, *bbox)
            window = from_bounds(left, bottom, right, top, src.transform)
            dn = src.read(1, window=window, out_shape=(GRID_SIZE, GRID_SIZE), resampling=Resampling.average).astype(float)
            dn[dn <= 0] = np.nan
            return np.clip((dn * cfg["scale"]) + cfg["offset"], 0.0, 1.0)

    blue = read_band("blue")
    red = read_band("red")
    nir = read_band("nir08")
    swir1 = read_band("swir16")
    swir2 = read_band("swir22")
    broadband = (0.356 * blue) + (0.130 * red) + (0.373 * nir) + (0.085 * swir1) + (0.072 * swir2) - 0.0018
    if np.all(np.isnan(broadband)):
        raise ValueError("All pixels in the Earth bounding box were masked.")
    return float(np.nanmean(np.clip(broadband, 0.0, 1.0)))


@lru_cache(maxsize=256)
def get_planetary_broadband_albedo(body, lat, lon):
    cfg = LIVE_DATASETS[body]
    R = cfg["radius_m"]
    half_m = (TILE_KM * 1000) / 2.0
    if body == "moon":
        raster_url, _ = get_moon_tile_url(lat, lon)
    else:
        raster_url = cfg["url"]

    src = _get_cached_dataset(raster_url)
    if src.crs is not None and src.crs.is_geographic:
        if src.bounds.left >= 0 and lon < 0:
            lon += 360.0
        elif src.bounds.left < 0 and lon > 180:
            lon -= 360.0
        cos_lat = max(np.cos(np.radians(lat)), 0.05)
        deg_per_m = 180.0 / (np.pi * R)
        half_lat_deg = half_m * deg_per_m
        half_lon_deg = (half_m * deg_per_m) / cos_lat
        window = from_bounds(lon - half_lon_deg, lat - half_lat_deg, lon + half_lon_deg, lat + half_lat_deg, src.transform)
    elif src.crs is not None:
        xs, ys = transform(f"+proj=longlat +R={R} +no_defs", src.crs, [lon], [lat])
        x, y = float(next(iter(xs))), float(next(iter(ys)))
        window = from_bounds(x - half_m, y - half_m, x + half_m, y + half_m, src.transform)
    else:
        cos_lat = max(np.cos(np.radians(lat)), 0.05)
        x = R * np.radians(lon)
        y = R * np.radians(lat)
        half_x = half_m / cos_lat
        window = from_bounds(x - half_x, y - half_m, x + half_x, y + half_m, src.transform)

    tile = src.read(1, window=window, out_shape=(GRID_SIZE, GRID_SIZE), resampling=Resampling.average, boundless=True, fill_value=np.nan).astype(float)
    if src.nodata is not None:
        tile[tile == src.nodata] = np.nan
    tile[tile < 0] = np.nan
    if np.all(np.isnan(tile)):
        raise ValueError(f"No valid {body} pixels found at ({lat}, {lon}). Check coordinates.")
    if body == "mars":
        return float(np.nanmean(np.clip(tile, 0.0, 1.0)))
    if body == "moon":
        scale = next(iter(src.scales), 1.0)
        offset = next(iter(src.offsets), 0.0)
        dtype = next(iter(src.dtypes))
        if dtype == "uint8":
            raise ValueError("Detected 8-bit visual image. Please use the float32 radiometric WAC_EMP .IMG file.")
        reflectance = (tile * scale) + offset
        broadband = reflectance * 0.75
        return float(np.nanmean(np.clip(broadband, 0.0, 1.0)))
