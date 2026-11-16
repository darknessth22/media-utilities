import { videoTools } from "./video.js";
import { pdfTools } from "./pdf.js";
import { imageTools, bgEraserTool } from "./image.js";

export const GROUPS = [
  { id: "video", name: "Video and audio", note: "FFmpeg, running inside this tab." },
  { id: "pdf", name: "PDF", note: "Combine, split and turn pages into pictures." },
  { id: "image", name: "Images", note: "Formats, sizes, colours, and AI background removal." },
  { id: "next", name: "Coming next", note: "The downloader needs a Videl server, so it comes after the in-browser tools." },
];

const nextTools = [
  {
    id: "download",
    group: "next",
    icon: "download",
    name: "Downloader",
    blurb: "Save videos and audio from YouTube, Instagram, TikTok and other sites.",
    soon: true,
    soonText: [
      "Video sites block downloads made straight from a browser tab, so the downloader needs a Videl server to do the fetching. That server is the next step.",
      "Until it's ready, the desktop app downloads from most video sites, with quality and time-range options.",
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

export const TOOLS = [...videoTools, ...pdfTools, ...imageTools, bgEraserTool, ...nextTools]
  .map((t) => ({ ...t, ...META[t.id] }));
export const toolById = (id) => TOOLS.find((t) => t.id === id);
