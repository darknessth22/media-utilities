import { videoTools } from "./video.js";
import { pdfTools } from "./pdf.js";
import { imageTools, bgEraserTool } from "./image.js";

export const GROUPS = [
  { id: "video", name: "Video and audio", note: "FFmpeg, running inside this tab." },
  { id: "pdf", name: "PDF", note: "Combine, split and turn pages into pictures." },
  { id: "image", name: "Images", note: "Formats, sizes, colours, and AI background removal." },
  { id: "download", name: "Downloader", note: "Hands links to the free Videl desktop app, which downloads on your own connection." },
];

// Video sites block downloads from browser tabs and from servers (tested in
// specs/002-downloader-server/spec.md), so this page hands the link to the
// desktop app (renderHandoff in main.js).
const downloadTools = [
  {
    id: "download",
    group: "download",
    icon: "download",
    name: "Downloader",
    blurb: "Send a YouTube, Instagram or TikTok link to the free Videl app to save the video or audio.",
    handoff: true,
    text: [
      "Paste a link and press Open in Videl. The Videl desktop app comes to the front with the link filled in: choose video or audio, the quality, and where to save.",
      "Video sites block downloads made from a browser tab, so the download runs in the app, on your own connection. The app has to be open on this computer.",
    ],
  },
];

// Accent colours match the desktop app (gui/pages/home_page.py _TOOL_COLOR),
// so a tool looks the same in both. "takes"/"gives" are shown on each tile.
const META = {
  convert: { color: "#22D3EE", takes: "Any video or audio", gives: "MP4, WebM, MOV, MKV, MP3, M4A, WAV, OGG" },
  trim: { color: "#F97316", takes: "Video or audio", gives: "The same format, or MP4" },
  compress: { color: "#22C55E", takes: "Video", gives: "Smaller MP4" },
  gif: { color: "#FACC15", takes: "Video", gives: "Animated GIF" },
  merge: { color: "#A855F7", takes: "Two or more videos", gives: "One MP4" },
  mux: { color: "#EC4899", takes: "Video, plus audio", gives: "Video with new sound" },
  split: { color: "#06B6D4", takes: "A long video or recording", gives: "Parts in the same format" },
  transform: { color: "#FB923C", takes: "Video", gives: "Rotated, cropped or smaller MP4" },
  "pdf-merge": { color: "#EF4444", takes: "Two or more PDFs", gives: "One PDF" },
  "pdf-split": { color: "#EF4444", takes: "PDF", gives: "PDF pages or ZIP" },
  "pdf-rotate": { color: "#EF4444", takes: "PDF", gives: "Rotated PDF" },
  "images-to-pdf": { color: "#38BDF8", takes: "JPG, PNG, WebP and more", gives: "PDF" },
  "pdf-to-images": { color: "#38BDF8", takes: "PDF", gives: "PNG or JPG per page" },
  "image-convert": { color: "#D946EF", takes: "Any image", gives: "JPG, PNG, WebP" },
  "pixel-art": { color: "#84CC16", takes: "Any image", gives: "Pixel-art PNG" },
  palette: { color: "#F43F5E", takes: "Any image", gives: "Swatch PNG and CSS" },
  download: { color: "#3B82F6", takes: "A link", gives: "Video or audio" },
  "bg-eraser": { color: "#10B981", takes: "Photos (JPG, PNG, WebP)", gives: "Transparent PNG, or a new background" },
};

// One-file tools that take a batch: each file is run on its own (workspace.js),
// and a free batch is one daily job of up to 10 files. Trim and GIF need a range
// per file, so they stay one file at a time; Image convert and the background
// remover take any number of files as one job.
const BATCH = new Set(["convert", "compress", "transform", "pixel-art", "pdf-rotate", "pdf-to-images"]);

export const TOOLS = [...videoTools, ...pdfTools, ...imageTools, bgEraserTool, ...downloadTools]
  .map((t) => ({ ...t, ...META[t.id], batch: BATCH.has(t.id) }));
export const toolById = (id) => TOOLS.find((t) => t.id === id);
