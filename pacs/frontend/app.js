"use strict";

const $ = (sel) => document.querySelector(sel);
const state = {
  studies: [],
  currentStudy: null,
  seriesList: [],
  currentSeries: null,
  instances: [],
  currentIndex: 0,
  tool: "wl",
  invert: false,
  wc: 40,
  ww: 400,
  zoom: 1,
  panX: 0,
  panY: 0,
  fitScale: 1,
  measurement: null,
};

const api = {
  async studies(params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v));
    const res = await fetch(`/api/studies?${qs}`);
    if (!res.ok) throw new Error("Failed to load studies");
    return res.json();
  },
  async study(uid) {
    const res = await fetch(`/api/studies/${uid}`);
    if (!res.ok) throw new Error("Failed to load study");
    return res.json();
  },
  async instances(seriesUid) {
    const res = await fetch(`/api/series/${seriesUid}/instances`);
    if (!res.ok) throw new Error("Failed to load instances");
    return res.json();
  },
  frameUrl(sopUid, wc, ww, invert) {
    const qs = new URLSearchParams({
      frame: "0",
      wc: String(wc),
      ww: String(ww),
      invert: String(invert),
    });
    return `/api/instances/${sopUid}/frame?${qs}`;
  },
  thumbUrl(seriesUid) {
    return `/api/series/${seriesUid}/thumbnail`;
  },
};

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("error", isError);
  el.classList.remove("hidden");
  setTimeout(() => el.classList.add("hidden"), 3500);
}

/* ---------------- Worklist ---------------- */

async function loadWorklist() {
  const params = {
    patient: $("#fPatient").value.trim(),
    modality: $("#fModality").value.trim(),
    date_from: $("#fDateFrom").value ? $("#fDateFrom").value.replaceAll("-", "") : "",
    date_to: $("#fDateTo").value ? $("#fDateTo").value.replaceAll("-", "") : "",
  };
  try {
    state.studies = await api.studies(params);
  } catch (e) {
    toast(e.message, true);
    return;
  }
  const rows = $("#studyRows");
  rows.innerHTML = "";
  $("#emptyMsg").classList.toggle("hidden", state.studies.length > 0);
  for (const s of state.studies) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${esc(s.patient_name)}</td>
      <td>${esc(s.patient_id)}</td>
      <td><span class="modality-badge">${esc(s.modality)}</span></td>
      <td>${fmtDate(s.study_date)}</td>
      <td>${esc(s.description || "—")}</td>
      <td>${esc(s.accession_number || "—")}</td>
      <td>${s.series_count}</td>
      <td>${s.image_count}</td>
      <td><button class="primary open-btn">Open</button></td>`;
    tr.addEventListener("click", () => openStudy(s.study_uid));
    rows.appendChild(tr);
  }
}

function esc(text) {
  const div = document.createElement("div");
  div.textContent = text == null ? "" : String(text);
  return div.innerHTML;
}

function fmtDate(d) {
  if (!d || d.length !== 8) return d || "—";
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
}

/* ---------------- Viewer ---------------- */

async function openStudy(studyUid) {
  try {
    state.currentStudy = await api.study(studyUid);
  } catch (e) {
    toast(e.message, true);
    return;
  }
  state.seriesList = state.currentStudy.series;
  $("#navViewer").disabled = false;
  showView("viewer");

  const bar = $("#seriesBar");
  bar.innerHTML = "";
  for (const s of state.seriesList) {
    const div = document.createElement("div");
    div.className = "thumb";
    div.innerHTML = `<img src="${api.thumbUrl(s.series_uid)}" alt="" />
      <div class="lbl">${esc(s.modality)} ${s.series_number}<br/>${s.image_count} img</div>`;
    div.addEventListener("click", () => selectSeries(s.series_uid));
    bar.appendChild(div);
  }
  if (state.seriesList.length > 0) {
    await selectSeries(state.seriesList[0].series_uid);
  }
}

async function selectSeries(seriesUid) {
  state.currentSeries = seriesUid;
  document.querySelectorAll(".thumb").forEach((el, i) => {
    el.classList.toggle("active", state.seriesList[i] && state.seriesList[i].series_uid === seriesUid);
  });
  try {
    state.instances = await api.instances(seriesUid);
  } catch (e) {
    toast(e.message, true);
    return;
  }
  state.currentIndex = 0;
  const slider = $("#sliceSlider");
  slider.max = String(Math.max(1, state.instances.length));
  slider.value = "1";
  state.measurement = null;
  const inst = state.instances[0];
  if (inst) {
    state.wc = inst.window_center || 40;
    state.ww = inst.window_width || 400;
  }
  await showInstance();
}

async function showInstance() {
  const inst = state.instances[state.currentIndex];
  if (!inst) return;
  const img = $("#frameImg");
  img.src = api.frameUrl(inst.sop_uid, state.wc, state.ww, state.invert);
  img.onload = () => {
    const svg = $("#overlay");
    svg.setAttribute("viewBox", `0 0 ${img.naturalWidth} ${img.naturalHeight}`);
    fitImage();
    redrawOverlay();
  };
  $("#sliceSlider").value = String(state.currentIndex + 1);
  $("#sliceLabel").textContent = `${state.currentIndex + 1}/${state.instances.length}`;
  updateCorners();
}

function updateCorners() {
  const s = state.currentStudy;
  const series = state.seriesList.find((x) => x.series_uid === state.currentSeries);
  const inst = state.instances[state.currentIndex];
  if (!s || !inst) return;
  $("#cornerTL").textContent =
    `${s.patient_name}\n${s.patient_id} · ${s.sex || "?"} · ${fmtDate(s.birth_date)}`;
  $("#cornerTR").textContent =
    `${s.description || ""}\n${series ? series.description || series.modality : ""}\n` +
    `Zoom ${Math.round(state.zoom * 100)}%`;
  $("#cornerBL").textContent =
    `WC ${Math.round(state.wc)} / WW ${Math.round(state.ww)}${state.invert ? " · INV" : ""}`;
  $("#cornerBR").textContent =
    `Img ${inst.instance_number} / ${state.instances.length}\n` +
    `${inst.rows}×${inst.cols} · ${inst.pixel_spacing[0].toFixed(2)} mm`;
}

function fitImage() {
  const img = $("#frameImg");
  const vp = $("#viewport");
  const scale = Math.min(
    (vp.clientWidth - 20) / img.naturalWidth,
    (vp.clientHeight - 20) / img.naturalHeight
  );
  state.fitScale = scale;
  state.zoom = 1;
  state.panX = (vp.clientWidth - img.naturalWidth * scale) / 2;
  state.panY = (vp.clientHeight - img.naturalHeight * scale) / 2;
  applyTransform();
}

function applyTransform() {
  const img = $("#frameImg");
  const s = state.fitScale * state.zoom;
  $("#stage").style.transform =
    `translate(${state.panX}px, ${state.panY}px) scale(${s})`;
  $("#stage").style.width = `${img.naturalWidth}px`;
  $("#stage").style.height = `${img.naturalHeight}px`;
  updateCorners();
}

let wlTimer = null;
function scheduleWlFetch() {
  clearTimeout(wlTimer);
  wlTimer = setTimeout(showInstance, 60);
}

/* Overlay measurement (image-pixel coordinates via SVG viewBox) */
function redrawOverlay() {
  const svg = $("#overlay");
  svg.innerHTML = "";
  const m = state.measurement;
  if (!m || !m.p2) return;
  const ns = "http://www.w3.org/2000/svg";
  const line = document.createElementNS(ns, "line");
  line.setAttribute("x1", m.p1.x);
  line.setAttribute("y1", m.p1.y);
  line.setAttribute("x2", m.p2.x);
  line.setAttribute("y2", m.p2.y);
  svg.appendChild(line);
  for (const p of [m.p1, m.p2]) {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", p.x);
    c.setAttribute("cy", p.y);
    c.setAttribute("r", 5);
    svg.appendChild(c);
  }
  const inst = state.instances[state.currentIndex];
  const dx = (m.p2.x - m.p1.x) * inst.pixel_spacing[1];
  const dy = (m.p2.y - m.p1.y) * inst.pixel_spacing[0];
  const mm = Math.sqrt(dx * dx + dy * dy);
  const label = document.createElementNS(ns, "text");
  label.setAttribute("x", (m.p1.x + m.p2.x) / 2 + 14);
  label.setAttribute("y", (m.p1.y + m.p2.y) / 2 - 14);
  label.textContent = `${mm.toFixed(1)} mm`;
  svg.appendChild(label);
}

function toImageCoords(evt) {
  const img = $("#frameImg");
  const rect = img.getBoundingClientRect();
  return {
    x: ((evt.clientX - rect.left) / rect.width) * img.naturalWidth,
    y: ((evt.clientY - rect.top) / rect.height) * img.naturalHeight,
  };
}

/* ---------------- Interaction ---------------- */

const viewport = $("#viewport");
let dragging = null;

viewport.addEventListener("mousedown", (e) => {
  e.preventDefault();
  if (state.tool === "length") {
    const p = toImageCoords(e);
    if (!state.measurement || state.measurement.p2) {
      state.measurement = { p1: p, p2: null };
    } else {
      state.measurement.p2 = p;
    }
    redrawOverlay();
    return;
  }
  dragging = { x: e.clientX, y: e.clientY, tool: state.tool };
});

window.addEventListener("mousemove", (e) => {
  if (!dragging) return;
  const dx = e.clientX - dragging.x;
  const dy = e.clientY - dragging.y;
  if (dragging.tool === "wl") {
    state.ww = Math.max(1, state.ww + dx * 4);
    state.wc = state.wc - dy * 4;
    dragging.x = e.clientX;
    dragging.y = e.clientY;
    $("#cornerBL").textContent =
      `WC ${Math.round(state.wc)} / WW ${Math.round(state.ww)}${state.invert ? " · INV" : ""}`;
    scheduleWlFetch();
  } else if (dragging.tool === "pan") {
    state.panX += dx;
    state.panY += dy;
    dragging.x = e.clientX;
    dragging.y = e.clientY;
    applyTransform();
  } else if (dragging.tool === "zoom") {
    state.zoom = Math.min(20, Math.max(0.05, state.zoom * (1 + dy * -0.005)));
    applyTransform();
    dragging.y = e.clientY;
  }
});

window.addEventListener("mouseup", () => (dragging = null));

viewport.addEventListener("wheel", (e) => {
  e.preventDefault();
  state.zoom = Math.min(20, Math.max(0.05, state.zoom * (e.deltaY < 0 ? 1.1 : 0.9)));
  applyTransform();
}, { passive: false });

window.addEventListener("keydown", (e) => {
  if ($("#viewerView").classList.contains("hidden")) return;
  if (e.key === "ArrowRight") stepInstance(1);
  else if (e.key === "ArrowLeft") stepInstance(-1);
  else if (e.key === "Escape") showView("worklist");
});

function stepInstance(delta) {
  if (state.instances.length === 0) return;
  state.currentIndex = Math.min(
    state.instances.length - 1,
    Math.max(0, state.currentIndex + delta)
  );
  state.measurement = null;
  showInstance();
}

/* ---------------- Navigation & wiring ---------------- */

function showView(name) {
  $("#worklistView").classList.toggle("hidden", name !== "worklist");
  $("#viewerView").classList.toggle("hidden", name !== "viewer");
  $("#navWorklist").classList.toggle("active", name === "worklist");
  $("#navViewer").classList.toggle("active", name === "viewer");
  if (name === "worklist") loadWorklist();
}

$("#navWorklist").addEventListener("click", () => showView("worklist"));
$("#navViewer").addEventListener("click", () => showView("viewer"));
$("#btnSearch").addEventListener("click", loadWorklist);
$("#btnReset").addEventListener("click", () => {
  $("#fPatient").value = "";
  $("#fModality").value = "";
  $("#fDateFrom").value = "";
  $("#fDateTo").value = "";
  loadWorklist();
});
[$("#fPatient"), $("#fModality")].forEach((el) =>
  el.addEventListener("keydown", (e) => e.key === "Enter" && loadWorklist())
);

$("#fileUpload").addEventListener("change", async (e) => {
  const files = [...e.target.files];
  if (files.length === 0) return;
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  try {
    const res = await fetch("/api/dicom/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error("Upload failed");
    const data = await res.json();
    toast(`Stored ${data.stored} DICOM object(s)`);
    loadWorklist();
  } catch (err) {
    toast(err.message, true);
  }
  e.target.value = "";
});

document.querySelectorAll(".tool[data-tool]").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.tool = btn.dataset.tool;
    document.querySelectorAll(".tool[data-tool]").forEach((b) =>
      b.classList.toggle("active", b === btn)
    );
    viewport.style.cursor =
      state.tool === "length" ? "crosshair" : state.tool === "pan" ? "grab" : "crosshair";
  });
});

document.querySelectorAll(".preset").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.wc = parseFloat(btn.dataset.wc);
    state.ww = parseFloat(btn.dataset.ww);
    showInstance();
  });
});

$("#btnInvert").addEventListener("click", () => {
  state.invert = !state.invert;
  $("#btnInvert").classList.toggle("active", state.invert);
  showInstance();
});

$("#btnReset").addEventListener("click", () => {
  state.invert = false;
  $("#btnInvert").classList.remove("active");
  fitImage();
  showInstance();
});

$("#btnPrev").addEventListener("click", () => stepInstance(-1));
$("#btnNext").addEventListener("click", () => stepInstance(1));
$("#sliceSlider").addEventListener("input", (e) => {
  state.currentIndex = parseInt(e.target.value, 10) - 1;
  state.measurement = null;
  showInstance();
});

window.addEventListener("resize", () => {
  if (!$("#viewerView").classList.contains("hidden")) fitImage();
});

loadWorklist();
