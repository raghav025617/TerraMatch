# TerraMatch
Lunar and Martian analog site-finding, mission planning, and interplanetary terrain analysis tool.


# Overview
TerraMatch is a web-based analog site finder that helps identify the closest matching Earth testing locations for specific sites on the Moon and Mars. Users upload an orbital terrain image and enter the target coordinates from NASA Moon Trek or Mars Trek. 

From there, TerraMatch calculates three core physical properties of the extraterrestrial site using NASA datasets and photoclinometric principles:
1. **Broadband Shortwave Albedo (BSA):** How much solar energy the surface reflects versus absorbs.
2. **Angular Vector Ruggedness Measure (VRM):** How bumpy and uneven the 3D terrain actually is.
3. **Rugged Hazard Area (RHA):** The percentage of the site that is too rough or hazardous for a rover or lander.

Once calculated, TerraMatch compares those three numbers against two custom 50-site Earth databases (earth-mars-match.json and lunar_sites.json) built during the event using Google Earth coordinates and orbital imagery. It then ranks the best matching Earth sites across three categories:
* **Best Maneuverability & Roughness Match:** Closest match in terrain bumpiness (VRM) and hazard coverage (RHA) for testing rover wheels, suspension, and landing gear.
* **Best Reflectivity & Thermal Match:** Closest match in surface albedo (BSA) for testing spacesuit insulation, thermal stress, and solar power generation.
* **Best Overall Twin:** Best all-around Earth analog taking all three metrics into account together.


## How the Math & Workflow Work

### 1. Streaming & Equalizing Albedo Across Worlds (`BSA.py`)
Different planetary satellites measure light in completely different ways, so we can't compare raw brightness directly. Instead of downloading multi-gigabyte global maps, `BSA.py` streams just a 30 km × 30 km patch around the entered coordinates using STAC APIs and HTTP byte-range requests, converting all three worlds onto a single 0.0 to 1.0 Broadband Shortwave Albedo (BSA) scale - (calibration math):
* **Earth (Landsat 8/9 C2 L2):** Fetches cloud-free (`<10%`) scenes via Microsoft Planetary Computer and combines five color bands using the Liang (2000) narrow-to-broadband formula:
  $$\text{BSA}_{\text{Earth}} = 0.356\text{Blue} + 0.130\text{Red} + 0.373\text{NIR} + 0.085\text{SWIR1} + 0.072\text{SWIR2} - 0.0018$$
* **Mars (MGS TES):** Streams native broadband spectrometer mosaics ($0.3\text{–}2.9\,\mu\text{m}$) directly from USGS Planetary Maps / NASA Mars Trek, which are already calibrated as true broadband albedo.
* **Moon (LROC WAC 643 nm):** Streams float32 radiometric mosaics from NASA PDS and multiplies the single-band normal reflectance by 0.75 ($\text{BSA}_{\text{Moon}} = R_{643} \times 0.75$). This combines the lunar phase integral ($q \approx 0.65$) with a spectral correction factor ($k \approx +0.10$) to put the Moon on the exact same physical scale as Earth and Mars.

### 2. Measuring Terrain Bumpiness & Danger Zones (`VRM-RHA.py`)
Simple slope measurements get tricked by smooth, tilted hillsides. To measure real 3D bumpiness from an orbital photo:
* **3D Surface Normals:** We denoise the grayscale image and use Scharr gradients ($dz/dx, dz/dy$) to point a 3D unit normal vector perpendicular to the ground at every pixel.
* **Angular VRM:** Across a sliding $15 \times 15$ pixel window, we average those 3D vectors into a resultant arrow $|\mathbf{R}|$ and measure how much they scatter using spherical angular dispersion:
  $$\text{VRM} = \frac{\arccos(|\mathbf{R}|)}{\pi / 2} \in [0.0, 1.0]$$
  Smooth ground scores near `0.0`, while chaotic crater rims and boulder fields score closer to `1.0`.
* **Rugged Hazard Area (RHA):** Any pixel with $\text{VRM} > 0.25$ is flagged as a rover hazard. The script calculates the exact percentage of unsafe area and renders a thermal image-like roughness mapping overlay directly on top of the orbital image.

### 3. Finding the Best Earth Match (`app.py`)
Because BSA, VRM, and RHA live on different numerical scales, `app.py` normalizes the difference between the target site and each of the 50 Earth candidates by dividing by their natural spans ($\Delta\text{BSA}/0.85$, $\Delta\text{VRM}/0.60$, $\Delta\text{RHA}/1.00$), then ranks the winners:
* **Maneuverability & Roughness Match:** $0.5 \cdot d_{\text{VRM}}^2 + 0.5 \cdot d_{\text{RHA}}^2$
* **Reflectivity & Thermal Match:** $|d_{\text{BSA}}|$
* **Best Overall Twin:** $0.5 \cdot d_{\text{BSA}}^2 + 0.25 \cdot d_{\text{VRM}}^2 + 0.25 \cdot d_{\text{RHA}}^2$


## Project Structure & How to Run
* **`app.py`:FastAPI backend that runs the image roughness analysis and live satellite albedo streaming in parallel.
* **`BSA.py`:Cloud streaming and cross-planetary albedo calibration script.
* **`VRM-RHA.py`: OpenCV gradient, 3D ruggedness, and safety heatmap generator.
* **`dashboard.html`: Frontend UI for uploading orbital images, entering coordinates, and viewing the leaderboard (alongside app.js and styles.css)

### Run Locally
(bash)
pip install fastapi uvicorn numpy opencv-python rasterio pystac-client planetary-computer python-multipart
uvicorn app:app --reload
Then open `http://127.0.0.1:8000` in your browser.


## Data Sources & AI Disclosure
* **Datasets Used:** NASA LROC PDS (Moon), USGS / NASA Mars Trek MGS TES (Mars), Microsoft Planetary Computer Landsat 8/9 C2 L2 (Earth), and Google Earth orbital imagery.
* **Use of AI:** I independently came up with the project idea, designed the software architecture and UI workflows, built and curated both 50-site Earth analog databases, chose the calibration constants, and ran all testing and validation. An AI coding assistant (Gemini- Free version) was used strictly to help write Python code for data processing and logic handling, debug programs, make the dahsboard UI, and clean up documentation formatting.
