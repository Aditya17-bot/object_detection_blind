// BlindAssist browser demo: the phone app's two models (yolov8n + the
// door/dustbin/stairs fine-tune) in ONNX Runtime Web, then logic.js, which is
// a parity-tested port of position.py / decision.py / detect_merge.py.
// Thresholds follow infer_server.py so the answer matches the app's backend.

import * as ort from "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/ort.min.mjs";
import * as L from "./logic.js";

ort.env.wasm.wasmPaths = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.30.0/dist/";

const COCO_NAMES = [
  "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
  "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog",
  "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella",
  "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball", "kite",
  "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket", "bottle",
  "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
  "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
  "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
  "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors",
  "teddy bear", "hair drier", "toothbrush",
];

const COCO_CONF = 0.6;
const CUSTOM_CONF = 0.4;
const CUSTOM_FLOOR = { door: 0.4, dustbin: 0.6 };
const NMS_IOU = 0.7; // ultralytics predict() default
const SIZE = 640;

const MODELS = [
  { url: "models/yolov8n.onnx", names: COCO_NAMES, conf: COCO_CONF, trusted: false },
  { url: "models/door_dustbin_stairs.onnx", names: ["door", "dustbin", "stairs"], conf: CUSTOM_CONF, trusted: true },
];

const PROX_COLOR = {
  "very close": "#ff5a4e", "close": "#ff9f1c", "medium": "#3ddc84", "far": "#3ddc84",
};

const $ = (id) => document.getElementById(id);
const stage = $("stage");
const canvas = $("canvas");
const ctx = canvas.getContext("2d");
const video = $("video");
const sayEl = $("say");

let sessions = null;
let current = null;        // the image or video being analysed
let live = false;
let lastSpoken = { text: "", at: 0 };

// ------------------------------------------------------------------ models

async function fetchWithProgress(url, onBytes) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  const total = Number(res.headers.get("content-length")) || 0;
  const reader = res.body.getReader();
  const chunks = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    got += value.length;
    onBytes(value.length, total);
  }
  const buf = new Uint8Array(got);
  let off = 0;
  for (const c of chunks) { buf.set(c, off); off += c.length; }
  return buf;
}

let backend = "wasm";

async function createSession(bytes) {
  if (navigator.gpu) {
    try {
      const s = await ort.InferenceSession.create(bytes, { executionProviders: ["webgpu"] });
      backend = "webgpu";
      return s;
    } catch { /* no usable adapter: fall through to wasm */ }
  }
  backend = "wasm";
  return ort.InferenceSession.create(bytes, { executionProviders: ["wasm"] });
}

async function loadModels() {
  const fill = $("loading-fill");
  const expected = 24.2e6; // both models, for the bar when no content-length
  let loaded = 0;
  const bytes = await Promise.all(MODELS.map((m) => fetchWithProgress(m.url, (n) => {
    loaded += n;
    fill.style.width = `${Math.min(100, (loaded / expected) * 100)}%`;
  })));
  $("loading-text").textContent = "Preparing models…";
  sessions = [];
  for (const b of bytes) sessions.push(await createSession(b));
  $("loading").hidden = true;
}

// --------------------------------------------------------------- detection

/** Letterbox like ultralytics: keep aspect, pad with grey 114, CHW floats. */
function preprocess(source, w, h) {
  const r = Math.min(SIZE / w, SIZE / h);
  const nw = Math.round(w * r);
  const nh = Math.round(h * r);
  const left = Math.round((SIZE - nw) / 2 - 0.1);
  const top = Math.round((SIZE - nh) / 2 - 0.1);
  const off = preprocess.canvas || (preprocess.canvas = new OffscreenCanvas(SIZE, SIZE));
  const octx = off.getContext("2d", { willReadFrequently: true });
  octx.fillStyle = "rgb(114,114,114)";
  octx.fillRect(0, 0, SIZE, SIZE);
  octx.drawImage(source, left, top, nw, nh);
  const { data } = octx.getImageData(0, 0, SIZE, SIZE);
  const plane = SIZE * SIZE;
  const input = new Float32Array(3 * plane);
  for (let i = 0; i < plane; i++) {
    input[i] = data[i * 4] / 255;
    input[plane + i] = data[i * 4 + 1] / 255;
    input[2 * plane + i] = data[i * 4 + 2] / 255;
  }
  return { tensor: new ort.Tensor("float32", input, [1, 3, SIZE, SIZE]), r, left, top };
}

function nms(dets) {
  dets.sort((a, b) => b.conf - a.conf);
  const kept = [];
  for (const d of dets) {
    if (!kept.some((k) => k.name === d.name && L.iou(k, d) > NMS_IOU)) kept.push(d);
  }
  return kept;
}

function decode(output, model, lb, w, h) {
  const [, channels, anchors] = output.dims;
  const out = output.data;
  const raw = [];
  for (let i = 0; i < anchors; i++) {
    let best = 0;
    let cls = -1;
    for (let c = 4; c < channels; c++) {
      const s = out[c * anchors + i];
      if (s > best) { best = s; cls = c - 4; }
    }
    if (cls < 0 || best < model.conf) continue;
    const name = model.names[cls];
    if (!L.TARGET_CLASSES.has(name) || best < (CUSTOM_FLOOR[name] ?? model.conf)) continue;
    const cx = out[i], cy = out[anchors + i], bw = out[2 * anchors + i], bh = out[3 * anchors + i];
    const clampX = (v) => Math.min(Math.max(v, 0), w);
    const clampY = (v) => Math.min(Math.max(v, 0), h);
    // python reads the box with int(), which truncates
    const x1 = Math.trunc(clampX((cx - bw / 2 - lb.left) / lb.r));
    const y1 = Math.trunc(clampY((cy - bh / 2 - lb.top) / lb.r));
    const x2 = Math.trunc(clampX((cx + bw / 2 - lb.left) / lb.r));
    const y2 = Math.trunc(clampY((cy + bh / 2 - lb.top) / lb.r));
    const det = { name, conf: best, px: [x1, y1, x2, y2], x1: x1 / w, y1: y1 / h, x2: x2 / w, y2: y2 / h };
    if (model.trusted) det.trusted_name = true;
    raw.push(det);
  }
  return nms(raw);
}

async function detect(source, w, h) {
  const lb = preprocess(source, w, h);
  let dets = [];
  for (let k = 0; k < MODELS.length; k++) {
    const session = sessions[k];
    const result = await session.run({ [session.inputNames[0]]: lb.tensor });
    dets = dets.concat(decode(result[session.outputNames[0]], MODELS[k], lb, w, h));
  }
  // each model only suppresses its own duplicates; one object can come back
  // under two names, so merge across models like infer_server.py does
  dets = L.mergeDetections(dets, CUSTOM_FLOOR, COCO_CONF);
  const infos = dets.map((d) => L.analyzeBox(d.name, d.conf, ...d.px, w, h, Boolean(d.trusted_name)));
  return { dets, infos };
}

function message(infos) {
  const mode = document.querySelector("input[name=mode]:checked").value;
  if (mode === "walk") {
    const ob = L.pickObstacle(infos);
    return ob ? L.walkMessage(ob, infos, true) : "Path looks clear";
  }
  if (mode === "find") {
    const target = $("target").value;
    return L.findMessage(L.findTarget(infos, target), target, true);
  }
  return L.summarizeScene(infos);
}

// ------------------------------------------------------------------ output

function draw(source, w, h, dets, infos) {
  canvas.width = w;
  canvas.height = h;
  ctx.drawImage(source, 0, 0, w, h);
  const unit = Math.min(w, h);
  ctx.strokeStyle = "rgba(200,200,200,.55)";
  ctx.lineWidth = Math.max(1, unit / 600);
  ctx.beginPath();
  for (const i of [1, 2]) {
    ctx.moveTo((w * i) / 3, 0); ctx.lineTo((w * i) / 3, h);
    ctx.moveTo(0, (h * i) / 3); ctx.lineTo(w, (h * i) / 3);
  }
  ctx.stroke();
  const font = Math.max(12, Math.round(unit / 30));
  ctx.font = `700 ${font}px "Atkinson Hyperlegible", system-ui, sans-serif`;
  ctx.textBaseline = "bottom";
  dets.forEach((d, k) => {
    const info = infos[k];
    const [x1, y1, x2, y2] = d.px;
    const color = PROX_COLOR[info.proximity];
    ctx.strokeStyle = color;
    ctx.lineWidth = Math.max(2, unit / 220);
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const label = `${info.name} | ${info.phrase} | ${info.proximity} ${info.confidence.toFixed(2)}`;
    const tw = ctx.measureText(label).width + 10;
    const ty = Math.max(y1, font + 8);
    ctx.fillStyle = color;
    ctx.fillRect(x1, ty - font - 8, tw, font + 8);
    ctx.fillStyle = "#000";
    ctx.fillText(label, x1 + 5, ty - 3);
  });
}

function list(infos) {
  const ol = $("det-list");
  ol.replaceChildren();
  $("det-count").textContent = infos.length ? `(${infos.length})` : "";
  if (!infos.length) {
    const li = document.createElement("li");
    li.className = "empty";
    li.textContent = "Nothing from the target classes.";
    ol.append(li);
    return;
  }
  for (const i of [...infos].sort((a, b) => b.area - a.area)) {
    const li = document.createElement("li");
    const dot = document.createElement("span");
    dot.className = "dot";
    dot.style.background = PROX_COLOR[i.proximity];
    const what = document.createElement("span");
    what.className = "what";
    what.textContent = i.name;
    const where = document.createElement("span");
    where.className = "where";
    where.textContent = `${L.clockPhrase(i.centerX)}, ${i.proximity}`;
    what.append(where);
    const num = document.createElement("span");
    num.className = "num";
    num.textContent = `${i.distanceM !== null ? `~${i.distanceM} m · ` : ""}${i.confidence.toFixed(2)}`;
    li.append(dot, what, num);
    ol.append(li);
  }
}

function speak(text, force) {
  if (!$("speak").checked || !window.speechSynthesis) return;
  const now = performance.now();
  // live video: repeat a message only after a pause, like the app's cooldown
  if (!force && text === lastSpoken.text && now - lastSpoken.at < 4000) return;
  if (!force && speechSynthesis.speaking) return;
  speechSynthesis.cancel();
  speechSynthesis.speak(new SpeechSynthesisUtterance(text));
  lastSpoken = { text, at: now };
}

async function analyse(force = true) {
  try {
    await runAnalysis(force);
  } catch (err) {
    console.error(err);
    sayEl.textContent = `Something went wrong: ${err.message}`;
  }
}

async function runAnalysis(force) {
  if (!sessions || !current) return;
  const isVideo = current === video;
  const w = isVideo ? video.videoWidth : current.naturalWidth;
  const h = isVideo ? video.videoHeight : current.naturalHeight;
  if (!w || !h) return;
  const t0 = performance.now();
  const { dets, infos } = await detect(current, w, h);
  const ms = performance.now() - t0;
  draw(current, w, h, dets, infos);
  const text = message(infos);
  if (sayEl.textContent !== text) sayEl.textContent = text;
  $("timing").textContent = `${Math.round(ms)} ms · ${backend}`;
  list(infos);
  speak(text, force);
}

// ------------------------------------------------------------------ inputs

function showImage(src) {
  stopCamera();
  const img = new Image();
  // Hugging Face serves repo files from a CDN origin; without CORS the
  // canvas is tainted and getImageData throws
  img.crossOrigin = "anonymous";
  img.onload = () => {
    current = img;
    stage.classList.add("has-image");
    analyse();
  };
  img.onerror = () => { sayEl.textContent = "Could not open that image."; };
  img.src = src;
}

async function startCamera() {
  try {
    video.srcObject = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment", width: { ideal: 1280 } }, audio: false,
    });
  } catch (err) {
    sayEl.textContent = "Camera unavailable. Upload a photo instead.";
    return;
  }
  await video.play();
  current = video;
  live = true;
  stage.classList.add("has-image");
  $("camera").setAttribute("aria-pressed", "true");
  $("camera").textContent = "Stop camera";
  const loop = async () => {
    if (!live) return;
    await analyse(false);
    requestAnimationFrame(loop);
  };
  loop();
}

function stopCamera() {
  if (!live) return;
  live = false;
  video.srcObject?.getTracks().forEach((t) => t.stop());
  video.srcObject = null;
  $("camera").setAttribute("aria-pressed", "false");
  $("camera").textContent = "Live camera";
}

function setMode(mode, target) {
  document.querySelector(`input[name=mode][value=${mode}]`).checked = true;
  $("target-wrap").hidden = mode !== "find";
  if (target) $("target").value = target;
}

function init() {
  const sel = $("target");
  for (const name of [...L.TARGET_CLASSES].sort()) sel.add(new Option(name, name));
  sel.value = "bottle";

  $("file").addEventListener("change", (e) => {
    const f = e.target.files[0];
    if (f) showImage(URL.createObjectURL(f));
  });
  $("camera").addEventListener("click", () => (live ? stopCamera() : startCamera()));
  document.querySelectorAll("input[name=mode]").forEach((r) =>
    r.addEventListener("change", () => { setMode(r.value); analyse(); }));
  sel.addEventListener("change", () => analyse());
  document.querySelectorAll(".ex").forEach((b) => b.addEventListener("click", () => {
    setMode(b.dataset.mode, b.dataset.target);
    showImage(b.dataset.src);
  }));

  stage.addEventListener("dragover", (e) => { e.preventDefault(); stage.classList.add("drag"); });
  stage.addEventListener("dragleave", () => stage.classList.remove("drag"));
  stage.addEventListener("drop", (e) => {
    e.preventDefault();
    stage.classList.remove("drag");
    const f = e.dataTransfer.files[0];
    if (f && f.type.startsWith("image/")) showImage(URL.createObjectURL(f));
  });
  window.addEventListener("paste", (e) => {
    const f = [...e.clipboardData.files].find((x) => x.type.startsWith("image/"));
    if (f) showImage(URL.createObjectURL(f));
  });

  loadModels().then(() => {
    if (current) analyse();
    else document.querySelector(".ex").click();
  }).catch((err) => {
    $("loading-text").textContent = `Could not load models: ${err.message}`;
  });
}

init();
