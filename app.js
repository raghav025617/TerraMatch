let currentMode = "mars";
const chipInput = document.getElementById("chipFile");
const dropzone = document.getElementById("dropzone");
const previewThumb = document.getElementById("previewThumb");
const dzTitle = document.getElementById("dzTitle");

const guidelinesBubble = document.getElementById("guidelinesBubble");
const guidelinesToggle = document.getElementById("guidelinesToggle");
const closeGuidelines = document.getElementById("closeGuidelines");

guidelinesToggle.addEventListener("click", function () {
  const isHidden = guidelinesBubble.classList.toggle("collapsed");
  guidelinesToggle.setAttribute("aria-expanded", String(!isHidden));
});

closeGuidelines.addEventListener("click", function () {
  guidelinesBubble.classList.add("collapsed");
  guidelinesToggle.setAttribute("aria-expanded", "false");
});

function setMode(mode) {
  currentMode = mode;
  const isMars = mode === "mars";
  document.getElementById("btnMarsMode").className = isMars ? "mode-btn active-mars" : "mode-btn";
  document.getElementById("btnMoonMode").className = !isMars ? "mode-btn active-moon" : "mode-btn";
  document.getElementById("coordLabel").textContent = isMars
    ? "1. Mars Target Coordinates (NASA Mars Trek)"
    : "1. Moon Target Coordinates (NASA Moon Trek)";
  document.getElementById("chipLabel").textContent = isMars
    ? "2. Mars Top-View Orbital Image"
    : "2. Moon Top-View Orbital Image";
  document.getElementById("latInput").placeholder = isMars ? "Latitude (e.g. 18.4447)" : "Latitude (e.g. -89.66)";
  document.getElementById("lonInput").placeholder = isMars ? "Longitude (e.g. 77.4508)" : "Longitude (e.g. 0.0)";

  const runBtn = document.getElementById("runBtn");
  runBtn.className = isMars ? "btn-primary" : "btn-primary moon-theme";
  runBtn.textContent = isMars ? "Run Mars Analysis & Match Earth Analogs" : "Run Moon Analysis & Match Earth Analogs";

  const tag = document.getElementById("activeDbTag");
  tag.textContent = isMars ? "MARS ORBITAL PROFILE" : "LUNAR ORBITAL PROFILE";
  tag.style.color = isMars ? "#fb923c" : "#38bdf8";
}

chipInput.addEventListener("change", function () {
  const file = chipInput.files.item(0);
  if (file) {
    dzTitle.textContent = file.name;
    const reader = new FileReader();
    reader.onload = function (e) {
      previewThumb.src = e.target.result;
      previewThumb.style.display = "inline-block";
    };
    reader.readAsDataURL(file);
  }
});

["dragenter", "dragover"].forEach(function (evt) {
  dropzone.addEventListener(evt, function (e) {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
});

["dragleave", "drop"].forEach(function (evt) {
  dropzone.addEventListener(evt, function (e) {
    e.preventDefault();
    dropzone.classList.remove("dragover");
  });
});

function renderTopAnalog(elId, items) {
  const container = document.getElementById(elId);
  container.innerHTML = "";
  if (!items || items.length === 0) {
    container.innerHTML = '<div class="empty-state">No matching Earth site found</div>';
    return;
  }

  const item = items[0];
  const card = document.createElement("div");
  card.className = "top-match-card";
  card.innerHTML =
    '<div class="match-top">' +
      '<span class="site-name"><span class="rank-num">#1</span> ' + item.name + '</span>' +
    '</div>' +
    '<div class="match-stats">' +
      '<div class="stat-line"><span>Broadband Shortwave Albedo</span><strong>' + Number(item.bsa).toFixed(4) + '</strong></div>' +
      '<div class="stat-line"><span>Vector Ruggedness Measure</span><strong>' + Number(item.vrm).toFixed(4) + '</strong></div>' +
      '<div class="stat-line"><span>Rugged Hazard Area</span><strong>' + (Number(item.hazard) * 100).toFixed(1) + '%</strong></div>' +
    '</div>';
  container.appendChild(card);
}

async function runAnalysis() {
  const lat = document.getElementById("latInput").value.trim();
  const lon = document.getElementById("lonInput").value.trim();
  const file = chipInput.files.item(0);
  const btn = document.getElementById("runBtn");
  const statusBanner = document.getElementById("statusBanner");

  if (!lat || !lon) return alert("Please enter both Latitude and Longitude.");
  if (!file) return alert("Please upload a cropped top-view orbital image.");

  btn.disabled = true;
  btn.textContent = "Analyzing " + currentMode.toUpperCase() + " Orbital Telemetry...";
  statusBanner.style.display = "none";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("mode", currentMode === "moon" ? "earth-to-moon" : "earth-to-mars");
  formData.append("body", currentMode);
  formData.append("lat", lat);
  formData.append("lon", lon);

  try {
    const res = await fetch("/api/analyze", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) {
      statusBanner.style.display = "flex";
      statusBanner.textContent = "ERROR — " + (data.detail || "Analysis pipeline failed.");
      return;
    }

    const m = data.metrics;
    document.getElementById("mBsa").textContent = m.bsa.toFixed(4);
    document.getElementById("mVrm").textContent = m.vrm.toFixed(4);
    document.getElementById("mVrmStd").textContent = "± " + m.std_vrm.toFixed(4) + " dispersion";
    document.getElementById("mHaz").textContent = (m.hazard * 100).toFixed(1) + "%";

    renderTopAnalog("lbDual", data.leaderboard.dual_best);
    renderTopAnalog("lbKin", data.leaderboard.kinematic_vrm_rha);
    renderTopAnalog("lbBsa", data.leaderboard.thermal_bsa);

    document.getElementById("overlayImg").src = data.overlay_base64;
    document.getElementById("overlayBox").style.display = "block";
  } catch (err) {
    statusBanner.style.display = "flex";
    statusBanner.textContent = "NETWORK ERROR — Could not reach local FastAPI server.";
  } finally {
    btn.disabled = false;
    btn.textContent = currentMode === "mars"
      ? "Run Mars Analysis & Match Earth Analogs"
      : "Run Moon Analysis & Match Earth Analogs";
  }
}
