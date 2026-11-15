import cv2
import numpy as np

def calculate_vrm(image_path, window_size=15, target_width=800, crop_bottom_pct=0.0):
    """
    Computes Absolute Angular VRM (Spherical Normal Dispersion) [0.0 to 1.0]
    using fixed 8-bit radiometric reflectance [0..1] so flat and rugged terrains
    are measured on the exact same physical scale.
    """
    img_bgr = cv2.imread(image_path)
    if img_bgr is None:
        raise FileNotFoundError(f"Could not load image at: {image_path}")

    h, w = img_bgr.shape[:2]

    if crop_bottom_pct > 0:
        cut_h = int(h * (1.0 - crop_bottom_pct))
        img_bgr = img_bgr[:cut_h, :]
        h, w = img_bgr.shape[:2]

    if target_width is not None and w != target_width:
        scale = target_width / float(w)
        new_h = int(h * scale)
        img_bgr = cv2.resize(img_bgr, (target_width, new_h), interpolation=cv2.INTER_AREA)

    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Mask pitch-black voids/shadows and saturated glare
    valid_mask = (img_gray > 5) & (img_gray < 250)

    # 1. Fixed radiometric reflectance [0.0..1.0] + Nyquist denoising (NO per-image Z-score)
    reflectance = cv2.GaussianBlur(img_gray / 255.0, (5, 5), 0)

    # 2. Orthogonal partial derivatives scaled to the analysis kernel baseline
    dz_dx = (cv2.Scharr(reflectance, cv2.CV_32F, 1, 0) / 16.0) * window_size
    dz_dy = (cv2.Scharr(reflectance, cv2.CV_32F, 0, 1) / 16.0) * window_size

    # 3. 3D unit surface normal vectors (nx, ny, nz)
    magnitude = np.sqrt(dz_dx**2 + dz_dy**2 + 1.0)
    nx = -dz_dx / magnitude
    ny = -dz_dy / magnitude
    nz = 1.0 / magnitude

    # 4. Resultant vector length |R| across local neighborhood
    ksize = (window_size, window_size)
    rx = cv2.blur(nx, ksize)
    ry = cv2.blur(ny, ksize)
    rz = cv2.blur(nz, ksize)
    resultant_length = np.clip(np.sqrt(rx**2 + ry**2 + rz**2), 0.0, 1.0)

    # 5. Angular Spherical Dispersion: arccos(|R|) / (pi/2) -> strictly [0.0, 1.0]
    angular_vrm_map = np.arccos(resultant_length) / (np.pi / 2.0)

    # Render heatmap
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
        "vrm_matrix": angular_vrm_map
    }

if __name__ == "__main__":
    results = calculate_vrm("EARTH-MARS-MATCH-DB-IMAGES/Barringer-Crater(USA).jpg", window_size=15)
    print(f"Angular VRM (Spherical Dispersion): {results['mean_vrm']} +/- {results['std_vrm']}")
    print(f"High-Ruggedness Hazard Area:        {results['hazard_fraction'] * 100:.1f}%")
    cv2.imwrite("terramatch_vrm_overlay.png", results["overlay_image"])
    print("Saved overlay to terramatch_vrm_overlay.png")

