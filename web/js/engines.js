// Engines load on first use only, so the home page stays light.

const CORE = "https://cdn.jsdelivr.net/npm/@ffmpeg/core@0.12.6/dist/esm";

let ffmpegPromise = null;

/** Download a file with byte progress and hand back a same-origin blob: URL. */
async function blobURL(url, type, onBytes) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Could not download the video engine (HTTP ${res.status}).`);
  const total = Number(res.headers.get("content-length")) || 0;
  const reader = res.body.getReader();
  const chunks = [];
  let loaded = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    loaded += value.length;
    onBytes?.(loaded, total);
  }
  return URL.createObjectURL(new Blob(chunks, { type }));
}

export function loadFFmpeg(onStatus = () => {}) {
  if (!ffmpegPromise) {
    ffmpegPromise = (async () => {
      const { FFmpeg } = await import("../vendor/ffmpeg/index.js");
      const ffmpeg = new FFmpeg();
      onStatus({ phase: "engine", loaded: 0, total: 0 });
      const coreURL = await blobURL(`${CORE}/ffmpeg-core.js`, "text/javascript");
      const wasmURL = await blobURL(`${CORE}/ffmpeg-core.wasm`, "application/wasm",
        (loaded, total) => onStatus({ phase: "engine", loaded, total }));
      await ffmpeg.load({ coreURL, wasmURL });
      return ffmpeg;
    })().catch((err) => { ffmpegPromise = null; throw err; });
  }
  return ffmpegPromise;
}

/** Stop the running job. The engine is reloaded (from cache) on the next run. */
export async function cancelFFmpeg() {
  if (!ffmpegPromise) return;
  const ffmpeg = await ffmpegPromise.catch(() => null);
  ffmpegPromise = null;
  ffmpeg?.terminate();
}

const TIME_RE = /time=\s*(\d+):(\d+):(\d+(?:\.\d+)?)/;

/**
 * Run one FFmpeg command.
 * inputs:   [{ name, file }] written into the in-memory filesystem first
 * output:   file name to read back
 * duration: expected output length in seconds, for the progress ratio
 */
export async function runFFmpeg({ inputs, args, output, type, duration, onProgress, onStatus, extraFiles = [] }) {
  const ffmpeg = await loadFFmpeg(onStatus);
  const tail = [];
  const onLog = ({ message }) => {
    tail.push(message);
    if (tail.length > 30) tail.shift();
    const m = TIME_RE.exec(message);
    if (m && duration > 0) {
      const t = Number(m[1]) * 3600 + Number(m[2]) * 60 + Number(m[3]);
      onProgress?.(Math.min(0.99, t / duration));
    }
  };
  ffmpeg.on("log", onLog);
  const written = [];
  try {
    onStatus?.({ phase: "reading" });
    for (const { name, file } of inputs) {
      await ffmpeg.writeFile(name, new Uint8Array(await file.arrayBuffer()));
      written.push(name);
    }
    for (const { name, data } of extraFiles) {
      await ffmpeg.writeFile(name, data);
      written.push(name);
    }
    onStatus?.({ phase: "working" });
    const code = await ffmpeg.exec(args);
    if (code !== 0) throw new Error(explain(tail));
    // A numbered output such as "part%03d.mp4" (the segment muxer) writes several
    // files: return all of them, in order, instead of one Blob.
    const prefix = output.includes("%") ? output.slice(0, output.indexOf("%")) : null;
    const names = prefix === null ? [output]
      : (await ffmpeg.listDir("/")).map((e) => e.name).filter((n) => n.startsWith(prefix)).sort();
    written.push(...names);
    const blobs = [];
    for (const name of names) blobs.push(new Blob([(await ffmpeg.readFile(name)).buffer], { type }));
    onProgress?.(1);
    return prefix === null ? blobs[0] : blobs;
  } finally {
    ffmpeg.off("log", onLog);
    for (const name of written) await ffmpeg.deleteFile(name).catch(() => {});
  }
}

/** Turn FFmpeg's last log lines into one readable sentence. */
function explain(lines) {
  const text = lines.join("\n");
  if (/does not contain any stream|Output file #0 does not contain/i.test(text)) return "The file has no stream of the kind this needs (for example, no audio track).";
  if (/Invalid data found|could not find codec parameters|moov atom not found/i.test(text)) return "This file couldn't be read. It may be damaged or in a format the browser engine doesn't support.";
  if (/Unsafe file name|Impossible to open|No such file/i.test(text)) return "The files couldn't be combined in this mode. Try the Compatible mode.";
  if (/Cannot allocate memory|out of memory|OOM/i.test(text)) return "The file is too large for the browser. Try a shorter clip or the desktop app.";
  const last = [...lines].reverse().find((l) => /error|invalid|failed/i.test(l));
  return last ? `Processing failed: ${last.trim()}` : "Processing failed. Try a different setting or file.";
}

// Background removal: ISNet (int8, 46 MB) on ONNX Runtime Web --------------------
// The model is split in two because static assets are capped at 25 MiB each;
// the parts are fetched and joined here. Same file as the desktop app's
// isnet-general-use, measured at 99.5-100% mask agreement with it.
const MODEL_PARTS = ["isnet-q8.part0", "isnet-q8.part1"];
const MODEL_BYTES = 45_902_969;
const SEG_SIZE = 1024;

let segPromise = null;

async function fetchModel(onStatus) {
  const out = new Uint8Array(MODEL_BYTES);
  let offset = 0;
  for (const part of MODEL_PARTS) {
    const res = await fetch(new URL(`../models/${part}`, import.meta.url));
    if (!res.ok) throw new Error(`Could not download the AI model (HTTP ${res.status}).`);
    const reader = res.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      out.set(value, offset);
      offset += value.length;
      onStatus({ phase: "model", loaded: offset, total: MODEL_BYTES });
    }
  }
  if (offset !== MODEL_BYTES) throw new Error("The AI model download was incomplete. Try again.");
  return out;
}

export function loadSegmenter(onStatus = () => {}) {
  if (!segPromise) {
    segPromise = (async () => {
      const ort = await import("../vendor/ort/ort.bundle.min.mjs");
      ort.env.wasm.wasmPaths = new URL("../vendor/ort/", import.meta.url).href;
      ort.env.logLevel = "error";               // unused-initializer warnings are harmless noise
      // Threads need cross-origin isolation (web/_headers): about 3.5x faster on 4 cores.
      ort.env.wasm.numThreads = self.crossOriginIsolated ? Math.min(4, navigator.hardwareConcurrency || 1) : 1;
      const model = await fetchModel(onStatus);
      onStatus({ phase: "runtime" });
      // CPU (WebAssembly) only: the int8 model's integer ops aren't supported on
      // WebGPU, and measured no faster there. Multi-threaded WASM is the fast path.
      try {
        const session = await ort.InferenceSession.create(model, { executionProviders: ["wasm"], graphOptimizationLevel: "all", logSeverityLevel: 3 });
        return { ort, session, device: "wasm" };
      } catch (err) {
        throw new Error(`The AI engine couldn't start in this browser. ${err?.message || ""}`.trim());
      }
    })().catch((err) => { segPromise = null; throw err; });
  }
  return segPromise;
}

/** Subject mask for an image: { size, alpha: Uint8ClampedArray(size*size) }. */
export async function segment(bitmap, onStatus = () => {}) {
  const { ort, session } = await loadSegmenter(onStatus);
  onStatus({ phase: "segment" });
  const S = SEG_SIZE;
  const canvas = new OffscreenCanvas(S, S);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(bitmap, 0, 0, S, S);             // stretched, as rembg does for ISNet
  const px = ctx.getImageData(0, 0, S, S).data;
  const input = new Float32Array(3 * S * S);
  for (let i = 0, j = 0; i < px.length; i += 4, j++) {
    input[j] = px[i] / 255 - 0.5;                // mean 0.5, std 1.0
    input[j + S * S] = px[i + 1] / 255 - 0.5;
    input[j + 2 * S * S] = px[i + 2] / 255 - 0.5;
  }
  const tensor = new ort.Tensor("float32", input, [1, 3, S, S]);
  const result = await session.run({ [session.inputNames[0]]: tensor });
  const prob = result[session.outputNames[0]].data;
  let lo = Infinity, hi = -Infinity;
  for (const v of prob) { if (v < lo) lo = v; if (v > hi) hi = v; }
  const alpha = new Uint8ClampedArray(S * S);
  const span = hi - lo || 1;
  for (let i = 0; i < alpha.length; i++) alpha[i] = ((prob[i] - lo) / span) * 255;
  return { size: S, alpha };
}

let pdfLib, pdfjs, zip;

export async function loadPdfLib() {
  pdfLib ??= import("../vendor/pdf-lib.esm.min.js");
  return pdfLib;
}

export async function loadPdfJs() {
  pdfjs ??= import("../vendor/pdfjs/pdf.min.mjs").then((mod) => {
    mod.GlobalWorkerOptions.workerSrc = new URL("../vendor/pdfjs/pdf.worker.min.mjs", import.meta.url).href;
    return mod;
  });
  return pdfjs;
}

export async function zipBlobs(items) {
  zip ??= import("../vendor/fflate.js");
  const { zipSync } = await zip;
  const files = {};
  const used = new Set();
  for (const { blob, name } of items) {
    let unique = name;
    for (let i = 2; used.has(unique); i++) unique = name.replace(/(\.[^.]*)?$/, ` (${i})$1`);
    used.add(unique);
    files[unique] = [new Uint8Array(await blob.arrayBuffer()), { level: 0 }];
  }
  return new Blob([zipSync(files)], { type: "application/zip" });
}
