// Image tools: everything runs on a canvas in the tab.
import { baseName, ext } from "../ui.js";

const IMAGES = "image/*";

// Same palettes as the desktop Pixel Art tool (core/pixel_art.py).
const PALETTES = {
  gameboy: ["#0F380F", "#306230", "#8BAC0F", "#9BBC0F"],
  pico8: ["#000000", "#1D2B53", "#7E2553", "#008751", "#AB5236", "#5F574F", "#C2C3C7", "#FFF1E8",
    "#FF004D", "#FFA300", "#FFEC27", "#00E436", "#29ADFF", "#83769C", "#FF77A8", "#FFCCAA"],
  sweetie16: ["#1A1C2C", "#5D275D", "#B13E53", "#EF7D57", "#FFCD75", "#A7F070", "#38B764", "#257179",
    "#29366F", "#3B5DC9", "#41A6F6", "#73EFF7", "#F4F4F4", "#94B0C2", "#566C86", "#333C57"],
  c64: ["#000000", "#FFFFFF", "#68372B", "#70A4B2", "#6F3D86", "#588D43", "#352879", "#B8C76F",
    "#6F4F25", "#433900", "#9A6759", "#444444", "#6C6C6C", "#9AD284", "#6C5EB5", "#959595"],
  grayscale: ["#000000", "#555555", "#AAAAAA", "#FFFFFF"],
};

const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].map((v) => (v + 0.5) / 16 - 0.5);

const hexToRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgbToHex = (rgb) => "#" + rgb.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("").toUpperCase();

export async function loadBitmap(file) {
  try {
    return await createImageBitmap(file);
  } catch {
    throw new Error(`${file.name} couldn't be opened as an image in this browser.`);
  }
}

function canvasOf(w, h) {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

const toBlob = (canvas, type, quality) => new Promise((resolve, reject) =>
  canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("This browser can't save that format."))), type, quality));

/** k-means++ over sampled pixels; returns k RGB centres sorted dark to light. */
export function kmeans(data, k, maxSamples = 12000) {
  const step = Math.max(1, Math.floor(data.length / 4 / maxSamples));
  const pts = [];
  for (let i = 0; i < data.length; i += 4 * step) if (data[i + 3] > 127) pts.push([data[i], data[i + 1], data[i + 2]]);
  if (!pts.length) return [[0, 0, 0]];
  k = Math.min(k, pts.length);
  const dist = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
  const centres = [pts[Math.floor(pts.length / 2)].slice()];
  while (centres.length < k) {
    let far = pts[0], best = -1;
    for (const p of pts) {
      const d = Math.min(...centres.map((c) => dist(p, c)));
      if (d > best) { best = d; far = p; }
    }
    centres.push(far.slice());
  }
  const assign = new Int32Array(pts.length);
  for (let iter = 0; iter < 12; iter++) {
    const sums = centres.map(() => [0, 0, 0, 0]);
    pts.forEach((p, i) => {
      let bi = 0, bd = Infinity;
      centres.forEach((c, j) => { const d = dist(p, c); if (d < bd) { bd = d; bi = j; } });
      assign[i] = bi;
      const s = sums[bi]; s[0] += p[0]; s[1] += p[1]; s[2] += p[2]; s[3]++;
    });
    sums.forEach((s, j) => { if (s[3]) centres[j] = [s[0] / s[3], s[1] / s[3], s[2] / s[3]]; });
  }
  const counts = centres.map((_, j) => assign.reduce((n, a) => n + (a === j), 0));
  return centres
    .map((c, j) => ({ c, n: counts[j] }))
    .filter((x) => x.n > 0)
    .sort((a, b) => b.n - a.n)
    .map((x) => x.c);
}

/** The Pixel Art pipeline: boost, box-downscale, map to palette (optionally dithered), nearest upscale. */
export function pixelate(bitmap, values) {
  const block = Number(values.block);
  const sw = Math.max(1, Math.round(bitmap.width / block));
  const sh = Math.max(1, Math.round(bitmap.height / block));
  const small = canvasOf(sw, sh);
  const sctx = small.getContext("2d", { willReadFrequently: true });
  sctx.imageSmoothingQuality = "high";
  sctx.filter = `saturate(${values.boost / 100}) contrast(${0.85 + values.boost / 650})`;
  sctx.drawImage(bitmap, 0, 0, sw, sh);
  sctx.filter = "none";
  const img = sctx.getImageData(0, 0, sw, sh);
  const d = img.data;
  const palette = values.palette === "auto" ? kmeans(d, Number(values.colours)) : PALETTES[values.palette].map(hexToRgb);
  const spread = values.dither === "ordered" ? 48 : 0;
  for (let y = 0; y < sh; y++) {
    for (let x = 0; x < sw; x++) {
      const i = (y * sw + x) * 4;
      const t = spread * BAYER[(y % 4) * 4 + (x % 4)];
      const r = d[i] + t, g = d[i + 1] + t, b = d[i + 2] + t;
      let best = palette[0], bd = Infinity;
      for (const p of palette) {
        const dd = (r - p[0]) ** 2 + (g - p[1]) ** 2 + (b - p[2]) ** 2;
        if (dd < bd) { bd = dd; best = p; }
      }
      d[i] = best[0]; d[i + 1] = best[1]; d[i + 2] = best[2];
    }
  }
  sctx.putImageData(img, 0, 0);
  const out = canvasOf(sw * block, sh * block);
  const octx = out.getContext("2d");
  octx.imageSmoothingEnabled = false;
  octx.drawImage(small, 0, 0, out.width, out.height);
  return { canvas: out, palette: palette.map(rgbToHex) };
}

export function extractPalette(bitmap, count) {
  const scale = Math.min(1, 240 / Math.max(bitmap.width, bitmap.height));
  const c = canvasOf(bitmap.width * scale, bitmap.height * scale);
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(bitmap, 0, 0, c.width, c.height);
  return kmeans(ctx.getImageData(0, 0, c.width, c.height).data, count).map(rgbToHex);
}

/** Swatch sheet: rows of up to 8 colours, hex code under each. */
function paletteStrip(colours) {
  const cols = Math.min(8, colours.length);
  const c = canvasOf(cols * 120, Math.ceil(colours.length / cols) * 160);
  const ctx = c.getContext("2d");
  ctx.fillStyle = "#FFF";
  ctx.fillRect(0, 0, c.width, c.height);
  ctx.font = "600 18px system-ui, sans-serif";
  colours.forEach((hex, i) => {
    const x = (i % cols) * 120, y = Math.floor(i / cols) * 160;
    ctx.fillStyle = hex;
    ctx.fillRect(x, y, 120, 120);
    ctx.fillStyle = "#111";
    ctx.fillText(hex, x + 14, y + 146);
  });
  return c;
}

const OUT_TYPES = { jpg: "image/jpeg", png: "image/png", webp: "image/webp" };

// Edge curves: remap the mask's soft ramp. Crisp suits products, Soft suits hair and fur.
const EDGES = { soft: [0, 1], balanced: [0.08, 0.92], crisp: [0.3, 0.7] };

/**
 * Put the subject on a new background.
 * mask: { size, alpha } from engines.segment(); maxSide limits the output (for fast previews).
 */
export function cutout(bitmap, mask, values, maxSide = Infinity) {
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const w = Math.max(1, Math.round(bitmap.width * scale));
  const hgt = Math.max(1, Math.round(bitmap.height * scale));

  // Mask -> canvas at the output size (smooth upscale), then read its alpha.
  const m = canvasOf(mask.size, mask.size);
  const mctx = m.getContext("2d");
  const mImg = mctx.createImageData(mask.size, mask.size);
  for (let i = 0; i < mask.alpha.length; i++) mImg.data[i * 4 + 3] = mask.alpha[i];
  mctx.putImageData(mImg, 0, 0);
  const fg = canvasOf(w, hgt);
  const fctx = fg.getContext("2d", { willReadFrequently: true });
  fctx.imageSmoothingQuality = "high";
  fctx.drawImage(m, 0, 0, w, hgt);
  const alpha = fctx.getImageData(0, 0, w, hgt).data;

  fctx.clearRect(0, 0, w, hgt);
  fctx.drawImage(bitmap, 0, 0, w, hgt);
  const img = fctx.getImageData(0, 0, w, hgt);
  const [lo, hi] = EDGES[values.edge] || EDGES.balanced;
  for (let i = 3; i < img.data.length; i += 4) {
    const a = alpha[i] / 255;
    img.data[i] = Math.max(0, Math.min(1, (a - lo) / (hi - lo))) * 255;
  }
  fctx.putImageData(img, 0, 0);

  if (values.background === "transparent") return fg;
  const out = canvasOf(w, hgt);
  const ctx = out.getContext("2d");
  if (values.background === "colour") {
    ctx.fillStyle = values.colour;
    ctx.fillRect(0, 0, w, hgt);
  } else {
    const blur = Math.max(6, Math.round(Math.max(w, hgt) / 45));
    ctx.filter = `blur(${blur}px)`;
    const pad = blur * 2;                         // bleed so the blur has no dark edges
    ctx.drawImage(bitmap, -pad, -pad, w + pad * 2, hgt + pad * 2);
    ctx.filter = "none";
  }
  ctx.drawImage(fg, 0, 0);
  return out;
}

export const bgEraserTool = {
  id: "bg-eraser",
  group: "image",
  icon: "bg_eraser",
  name: "Remove background",
  blurb: "Cut the subject out of a photo with an AI model that runs on your device. Drag the slider to compare.",
  accept: IMAGES,
  multiple: true,
  preview: "compare",
  action: "Save",
  fields: [
    { key: "background", type: "seg", label: "New background", value: "transparent",
      options: [["transparent", "Transparent"], ["colour", "Colour"], ["blur", "Blurred photo"]] },
    { key: "colour", type: "color", label: "Colour", value: "#FFFFFF", when: (v) => v.background === "colour" },
    { key: "edge", type: "seg", label: "Edges", value: "balanced",
      options: [["soft", "Soft"], ["balanced", "Balanced"], ["crisp", "Crisp"]],
      hint: "Soft keeps fine hair and fur. Crisp gives clean outlines for products." },
    { key: "format", type: "seg", label: "Save as", value: "jpg",
      options: [["jpg", "JPG"], ["png", "PNG"]], when: (v) => v.background !== "transparent",
      hint: "Transparent backgrounds are always saved as PNG." },
  ],
  live(bitmap, values, mask) {
    return { canvas: cutout(bitmap, mask, values, 1400) };
  },
  async run({ files, values, progress, prepare }) {
    const results = [];
    const format = values.background === "transparent" ? "png" : values.format;
    for (const [i, file] of files.entries()) {
      const bmp = await loadBitmap(file);
      const mask = await prepare(file, bmp);
      const canvas = cutout(bmp, mask, values);
      bmp.close();
      const blob = await toBlob(canvas, OUT_TYPES[format], 0.92);
      results.push({ blob, name: `${baseName(file.name)}-cutout.${format}` });
      progress((i + 1) / files.length);
    }
    return results;
  },
};

export const imageTools = [
  {
    id: "image-convert",
    group: "image",
    icon: "image_editor",
    name: "Convert and resize",
    blurb: "Change image format, shrink dimensions or reduce file size, for one image or many.",
    accept: IMAGES,
    multiple: true,
    preview: "image",
    action: "Convert",
    fields: [
      { key: "format", type: "seg", label: "Save as", value: "webp",
        options: [["keep", "Same format"], ["jpg", "JPG"], ["png", "PNG"], ["webp", "WebP"]] },
      { key: "quality", type: "range", label: "Quality", value: 82, min: 40, max: 100, step: 1, unit: "%",
        when: (v) => v.format !== "png" },
      { key: "maxSide", type: "seg", label: "Longest side", value: "keep",
        options: [["keep", "Keep"], ["3840", "3840 px"], ["1920", "1920 px"], ["1280", "1280 px"], ["800", "800 px"]],
        custom: { value: "1600", min: 16, max: 10000, unit: "px", whole: true } },
    ],
    async run({ files, values, progress }) {
      const results = [];
      for (const [i, file] of files.entries()) {
        const bmp = await loadBitmap(file);
        const limit = values.maxSide === "keep" ? Infinity : Number(values.maxSide);
        const scale = Math.min(1, limit / Math.max(bmp.width, bmp.height));
        const c = canvasOf(bmp.width * scale, bmp.height * scale);
        const ctx = c.getContext("2d");
        let format = values.format === "keep" ? (ext(file.name) === "jpeg" ? "jpg" : ext(file.name)) : values.format;
        if (!OUT_TYPES[format]) format = "png";
        if (format === "jpg") { ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, c.width, c.height); }
        ctx.imageSmoothingQuality = "high";
        ctx.drawImage(bmp, 0, 0, c.width, c.height);
        bmp.close();
        const blob = await toBlob(c, OUT_TYPES[format], values.quality / 100);
        results.push({ blob, name: `${baseName(file.name)}.${format}`, compareTo: file.size });
        progress((i + 1) / files.length);
      }
      return results;
    },
  },

  {
    id: "pixel-art",
    group: "image",
    icon: "pixel_art",
    name: "Pixel art",
    blurb: "Turn a photo into crisp pixel art with a retro colour palette. The preview updates as you change settings.",
    accept: IMAGES,
    preview: "live",
    action: "Save PNG",
    fields: [
      { key: "block", type: "range", label: "Pixel size", value: 8, min: 2, max: 32, step: 1, unit: " px" },
      { key: "palette", type: "select", label: "Palette", value: "auto",
        options: [["auto", "From the image"], ["pico8", "PICO-8"], ["sweetie16", "Sweetie 16"], ["gameboy", "Game Boy"], ["c64", "Commodore 64"], ["grayscale", "Grayscale"]] },
      { key: "colours", type: "range", label: "Colours", value: 16, min: 2, max: 32, step: 1, unit: "",
        when: (v) => v.palette === "auto" },
      { key: "dither", type: "seg", label: "Dithering", value: "none", options: [["none", "Off"], ["ordered", "Retro pattern"]] },
      { key: "boost", type: "range", label: "Colour boost", value: 120, min: 80, max: 180, step: 5, unit: "%" },
    ],
    live(bitmap, values) {
      return pixelate(bitmap, values);
    },
    async run({ files: [file], values }) {
      const bmp = await loadBitmap(file);
      const { canvas } = pixelate(bmp, values);
      bmp.close();
      return [{ blob: await toBlob(canvas, "image/png"), name: `${baseName(file.name)}-pixel.png` }];
    },
  },

  {
    id: "palette",
    group: "image",
    icon: "palette",
    name: "Colour palette",
    blurb: "Pull the main colours out of an image. Click a colour to copy its hex code.",
    accept: IMAGES,
    preview: "live",
    action: "Save palette",
    fields: [
      { key: "count", type: "range", label: "Number of colours", value: 6, min: 3, max: 32, step: 1, unit: "" },
    ],
    live(bitmap, values) {
      return { palette: extractPalette(bitmap, Number(values.count)) };
    },
    async run({ files: [file], values }) {
      const bmp = await loadBitmap(file);
      const colours = extractPalette(bmp, Number(values.count));
      bmp.close();
      const css = `:root {\n${colours.map((c, i) => `  --colour-${i + 1}: ${c};`).join("\n")}\n}\n`;
      return [
        { blob: await toBlob(paletteStrip(colours), "image/png"), name: `${baseName(file.name)}-palette.png` },
        { blob: new Blob([css], { type: "text/css" }), name: `${baseName(file.name)}-palette.css` },
      ];
    },
  },
];
