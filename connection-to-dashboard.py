import asyncio
import base64
import importlib.util
import json
import os
from pathlib import Path
from typing import Optional

os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
os.environ.setdefault("CPL_VSIL_CURL_ALLOWED_EXTENSIONS", ".tif,.TIF,.img,.IMG")

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bsa_mod = load_module("bsa_mod", BASE_DIR / "BSA.py")
vrm_mod = load_module("vrm_mod", BASE_DIR / "VRM-RHA.py")

with open(BASE_DIR / "earth-mars-match.json", "r", encoding="utf-8") as f:
    EARTH_MARS_DB = json.load(f)

with open(BASE_DIR / "lunar_sites.json", "r", encoding="utf-8") as f:
    LUNAR_SITES_DB = json.load(f)

app = FastAPI(title="TerraMatch Planetary Analog API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def compute_vrm_from_bytes(image_bytes: bytes) -> dict:
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Invalid or unreadable orbital image file.")
    if hasattr(vrm_mod, "calculate_vrm_array"):
        return vrm_mod.calculate_vrm_array(img_bgr)
    return _fast_vrm_pipeline(img_bgr)


def _fast_vrm_pipeline(img_bgr: np.ndarray, window_size: int = 15, target_width: int = 800) -> dict:
    h, w = img_bgr.shape[:2]
    if target_width is not None and w != target_width:
        scale = target_width / float(w)
        img_bgr = cv2.resize(img_bgr, (target_width, int(h * scale)), interpolation=cv2.INTER_AREA)

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    valid_mask = (img_gray > 5) & (img_gray < 250)

    reflectance = cv2.GaussianBlur(img_gray / 255.0, (5, 5), 0)
    dz_dx = (cv2.Scharr(reflectance, cv2.CV_32F, 1, 0) / 16.0) * window_size
    dz_dy = (cv2.Scharr(reflectance, cv2.CV_32F, 0, 1) / 16.0) * window_size

    magnitude = np.sqrt(dz_dx**2 + dz_dy**2 + 1.0)
    nx = -dz_dx / magnitude
    ny = -dz_dy / magnitude
    nz = 1.0 / magnitude

    ksize = (window_size, window_size)
    rx = cv2.blur(nx, ksize)
    ry = cv2.blur(ny, ksize)
    rz = cv2.blur(nz, ksize)
    resultant_length = np.clip(np.sqrt(rx**2 + ry**2 + rz**2), 0.0, 1.0)

    angular_vrm_map = np.arccos(resultant_length) / (np.pi / 2.0)

    heat_8bit = np.clip(angular_vrm_map * 255.0, 0, 255).astype(np.uint8)
    thermal_color = cv2.applyColorMap(heat_8bit, cv2.COLORMAP_TURBO)
    thermal_color[~valid_mask] = (40, 40, 40)
    overlay = cv2.addWeighted(img_bgr, 0.50, thermal_color, 0.50, 0)

    valid_vrm = angular_vrm_map[valid_mask]
    mean_vrm = float(np.mean(valid_vrm)) if valid_vrm.size > 0 else 0.0
    std_vrm = float(np.std(valid_vrm)) if valid_vrm.size > 0 else 0.0
    hazard_frac = float(np.mean(valid_vrm > 0.25)) if valid_vrm.size > 0 else 0.0

    return {
        "mean_vrm": round(mean_vrm, 4),
        "std_vrm": round(std_vrm, 4),
        "hazard_fraction": round(hazard_frac, 4),
        "overlay_image": overlay,
    }


def fetch_bsa_sync(body: str, lat: float, lon: float) -> float:
    body_clean = body.lower()
    if body_clean == "earth":
        return round(float(bsa_mod.get_earth_broadband_albedo(lat, lon)), 4)
    return round(float(bsa_mod.get_planetary_broadband_albedo(body_clean, lat, lon)), 4)


def rank_analogs(db: list, target_bsa: float, target_vrm: float, target_hazard: float):
    bsa_span, vrm_span, haz_span = 0.85, 0.60, 1.00

    def kin_dist(site):
        d_vrm = (float(site.get("vrm", 0.0)) - target_vrm) / vrm_span
        d_haz = (float(site.get("hazard", 0.0)) - target_hazard) / haz_span
        return 0.5 * d_vrm**2 + 0.5 * d_haz**2

    def bsa_dist(site):
        return abs(float(site.get("bsa", 0.0)) - target_bsa) / bsa_span

    def dual_dist(site):
        d_bsa = (float(site.get("bsa", 0.0)) - target_bsa) / bsa_span
        d_vrm = (float(site.get("vrm", 0.0)) - target_vrm) / vrm_span
        d_haz = (float(site.get("hazard", 0.0)) - target_hazard) / haz_span
        return 0.5 * d_bsa**2 + 0.25 * d_vrm**2 + 0.25 * d_haz**2

    return {
        "dual_best": [min(db, key=dual_dist)] if db else [],
        "kinematic_vrm_rha": [min(db, key=kin_dist)] if db else [],
        "thermal_bsa": [min(db, key=bsa_dist)] if db else [],
    }


@app.post("/api/analyze")
async def analyze_target(
    file: UploadFile = File(...),
    mode: str = Form("earth-to-mars"),
    body: str = Form("mars"),
    lat: float = Form(...),
    lon: float = Form(...),
    fallback_bsa: Optional[float] = Form(None),
):
    image_bytes = await file.read()

    vrm_task = asyncio.to_thread(compute_vrm_from_bytes, image_bytes)
    bsa_task = asyncio.to_thread(fetch_bsa_sync, body, lat, lon)

    vrm_result, bsa_result = await asyncio.gather(vrm_task, bsa_task, return_exceptions=True)

    if isinstance(vrm_result, Exception):
        raise HTTPException(status_code=400, detail=f"Image analysis failed: {vrm_result}")

    if isinstance(bsa_result, Exception):
        if fallback_bsa is None:
            raise HTTPException(status_code=502, detail=f"Orbital albedo stream failed: {bsa_result}")
        bsa_val = fallback_bsa
    else:
        bsa_val = bsa_result

    mean_vrm = float(vrm_result["mean_vrm"])
    hazard_frac = float(vrm_result["hazard_fraction"])

    _, buffer = cv2.imencode(".jpg", vrm_result["overlay_image"], [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    overlay_b64 = "data:image/jpeg;base64," + base64.b64encode(buffer).decode("utf-8")

    active_db = LUNAR_SITES_DB if mode == "earth-to-moon" else EARTH_MARS_DB
    leaderboard = rank_analogs(active_db, bsa_val, mean_vrm, hazard_frac)

    return {
        "metrics": {
            "bsa": bsa_val,
            "vrm": mean_vrm,
            "std_vrm": float(vrm_result["std_vrm"]),
            "hazard": hazard_frac,
        },
        "overlay_base64": overlay_b64,
        "leaderboard": leaderboard,
    }


@app.get("/static/{filename}")
def serve_static(filename: str):
    return FileResponse(BASE_DIR / filename)


@app.get("/")
def serve_index():
    return FileResponse(BASE_DIR / "dashboard.html")