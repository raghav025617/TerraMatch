# TerraMatch
Lunar and Martian analog site-finding, mission planning, and interplanetary terrain analysis tool.

## Overview
Testing a rover, lander, or spacesuit in a generic desert on Earth leads to costly hardware failures if the ground geometry and surface heat don't match the destination planet. **TerraMatch** solves this by helping mission planners find the closest matching Earth training sites for specific locations on the Moon and Mars.

Users simply enter target coordinates from **NASA Moon Trek** or **Mars Trek** and upload a top-view orbital terrain image. TerraMatch analyzes the extraterrestrial site, compares it against two custom databases of **50 validated Earth analog sites** (`earth-mars-match.json` and `lunar_sites.json`) built using Google Earth coordinates and orbital imagery, and ranks the #1 terrestrial matches across three engineering categories.

## How It Works (Simple Breakdown)

### 1. Calculating and Equalizing Solar Reflectivity Across Worlds (`BSA.py`)
Different space telescopes and satellites measure light in different ways, so raw image brightness can't be compared directly across planets. Instead of downloading massive global maps, TerraMatch streams just a 30 km × 30 km patch around the user's coordinates directly from NASA and USGS servers, converting all three worlds onto a single **Broadband Shortwave Albedo (BSA)** scale (`0.0` to `1.0`):
* **Earth (Landsat 8/9):** Combines five separate color bands from cloud-free satellite scenes using **Liang's (2000)** narrow-to-broadband calibration formula.
* **Mars (MGS TES):** Pulls directly from NASA's Mars Global Surveyor spectrometer mosaic, which already measures full broadband solar reflectivity.
* **Moon (LROC WAC):** Streams NASA PDS lunar mosaics and equalizes the single-band brightness using **lunar phase-integral scaling (`0.65`)** plus a **spectral correction factor (`0.10`)**—giving a `0.75` multiplier that puts lunar dust on the exact same physical scale as Earth and Mars.

### 2. Measuring 3D Terrain Bumpiness via Photoclinometry (`VRM-RHA.py`)
Simple slope filters get tricked by smooth, tilted hillsides. To measure true 3D surface roughness from a top-down orbital photo, TerraMatch uses **photoclinometry** (shape-from-shading):
* **3D Surface Normals:** After filtering out sensor noise, pitch-black shadows, and camera glare, the tool tracks how pixel brightness changes across neighboring pixels to point an invisible 3D direction arrow perpendicular to the ground at every spot.
* **Angular Vector Ruggedness Measure (VRM):** Across a sliding 15 × 15 pixel window, it checks how much those 3D arrows scatter. On smooth ground, all arrows point the same way (score near `0.0`); on rocky crater rims, they point in every direction (score closer to `1.0`).
* **Rugged Hazard Area (RHA):** Any patch exceeding a `0.25` ruggedness threshold is flagged as a rover hazard. TerraMatch calculates the exact percentage of dangerous ground and paints a high-contrast roughness-highlighting map overlay right over the orbital image.

### 3. Matching & Ranking Earth Analogs (`connection-to-dashboard.py`)
To compare the three metrics fairly on the same scale, the app divides each difference by the maximum range observed across our Earth analog databases (`0.85` for BSA, `0.60` for VRM, and `1.00` for RHA), then scores every site using a weighted distance formula to crown the `#1` match in three categories:
* **Best Maneuverability & Roughness Match:** Closest match in terrain bumpiness (VRM) and hazard coverage (RHA) for testing rover wheels, suspension, and landing gear.
* **Best Reflectivity & Thermal Match:** Closest match in surface solar reflectivity (BSA) for testing spacesuit insulation, heat stress, and solar panels.
* **Best Overall Twin:** Best all-around Earth analog balancing 50% albedo/reflective properties and 50% terrain geometry (25% VRM + 25% RHA).

## Project Files & Local Setup
* **`connection-to-dashboard.py`:** FastAPI server that runs the image analysis and live satellite streaming in parallel and ranks the Earth matches.
* **`BSA.py`:** Cloud streaming and cross-planetary albedo calibration script.
* **`VRM-RHA.py`:** Photoclinometry, 3D ruggedness, and safety heatmap generator.
* **`dashboard.html`, `app.js`, `styles.css`:** Interactive web dashboard for entering coordinates, uploading orbital images, and viewing results.

### Run Locally
```bash
pip install fastapi uvicorn numpy opencv-python rasterio pystac-client planetary-computer python-multipart
uvicorn connection-to-dashboard:app --reload
```
Open `http://127.0.0.1:8000` in your browser.

## Data Sources & AI Disclosure
* **Datasets Used:** NASA LROC PDS (Moon), USGS / NASA Mars Trek MGS TES (Mars), Microsoft Planetary Computer Landsat 8/9 C2 L2 (Earth), and Google Earth orbital imagery.
* **Use of AI:** I independently came up with the project idea, designed the software architecture and UI workflows, built and curated both 50-site Earth analog databases, chose the calibration constants, and ran all testing and validation. An AI coding assistant (Gemini - Free version) was used strictly to help write Python code for data processing and logic handling, debug programs, build the dashboard UI, and clean up documentation formatting.

