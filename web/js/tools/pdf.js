// PDF tools: pdf-lib for page operations, pdf.js for rendering pages to images.
import { loadPdfJs, loadPdfLib } from "../engines.js";
import { baseName } from "../ui.js";

const PDF = "application/pdf,.pdf";

/** "1-3, 5, 8-" -> zero-based page indexes, validated against the page count. */
export function parseRanges(text, count) {
  const pages = [];
  for (const part of text.split(",").map((s) => s.trim()).filter(Boolean)) {
    const m = /^(\d+)?\s*(-)?\s*(\d+)?$/.exec(part);
    if (!m || (!m[1] && !m[3])) throw new Error(`"${part}" isn't a page or range. Use something like 1-3, 5.`);
    const from = m[1] ? Number(m[1]) : 1;
    const to = m[2] ? (m[3] ? Number(m[3]) : count) : from;
    if (from < 1 || to > count || from > to) throw new Error(`Pages ${part} are outside this ${count}-page PDF.`);
    for (let p = from; p <= to; p++) pages.push(p - 1);
  }
  if (!pages.length) throw new Error("Enter at least one page.");
  return pages;
}

async function openPdf(file) {
  const { PDFDocument } = await loadPdfLib();
  try {
    return await PDFDocument.load(await file.arrayBuffer(), { ignoreEncryption: false });
  } catch (err) {
    if (/encrypted/i.test(err.message)) throw new Error(`${file.name} is password-protected. Remove the password first.`);
    throw new Error(`${file.name} couldn't be read as a PDF.`);
  }
}

const pdfBlob = (bytes) => new Blob([bytes], { type: "application/pdf" });

export const pdfTools = [
  {
    id: "pdf-merge",
    group: "pdf",
    icon: "document",
    name: "Merge PDFs",
    blurb: "Combine several PDFs into one file, in the order you choose.",
    accept: PDF,
    multiple: true,
    minFiles: 2,
    reorder: true,
    action: "Merge",
    fields: [],
    async run({ files, progress }) {
      const { PDFDocument } = await loadPdfLib();
      const out = await PDFDocument.create();
      for (const [i, file] of files.entries()) {
        const doc = await openPdf(file);
        const pages = await out.copyPages(doc, doc.getPageIndices());
        pages.forEach((p) => out.addPage(p));
        progress((i + 1) / files.length);
      }
      return [{ blob: pdfBlob(await out.save()), name: `${baseName(files[0].name)}-merged.pdf` }];
    },
  },

  {
    id: "pdf-split",
    group: "pdf",
    icon: "document",
    name: "Split PDF",
    blurb: "Take out the pages you need, or save every page as its own PDF.",
    accept: PDF,
    action: "Split",
    fields: [
      { key: "mode", type: "seg", label: "Split into", value: "pick",
        options: [["pick", "Chosen pages"], ["each", "One file per page"]] },
      { key: "pages", type: "text", label: "Pages", value: "1-3", placeholder: "1-3, 5, 8-",
        hint: "Ranges and single pages, separated by commas. 8- means page 8 to the end.",
        when: (v) => v.mode === "pick" },
    ],
    async run({ files: [file], values, progress }) {
      const { PDFDocument } = await loadPdfLib();
      const doc = await openPdf(file);
      const count = doc.getPageCount();
      if (values.mode === "pick") {
        const out = await PDFDocument.create();
        const pages = await out.copyPages(doc, parseRanges(values.pages, count));
        pages.forEach((p) => out.addPage(p));
        return [{ blob: pdfBlob(await out.save()), name: `${baseName(file.name)}-pages.pdf` }];
      }
      const results = [];
      for (let i = 0; i < count; i++) {
        const out = await PDFDocument.create();
        const [page] = await out.copyPages(doc, [i]);
        out.addPage(page);
        results.push({ blob: pdfBlob(await out.save()), name: `${baseName(file.name)}-page-${i + 1}.pdf` });
        progress((i + 1) / count);
      }
      return results;
    },
  },

  {
    id: "pdf-rotate",
    group: "pdf",
    icon: "spatial",
    name: "Rotate pages",
    blurb: "Turn sideways or upside-down pages the right way round.",
    accept: PDF,
    action: "Rotate",
    fields: [
      { key: "angle", type: "seg", label: "Rotate by", value: "90",
        options: [["90", "90° right"], ["180", "180°"], ["270", "90° left"]] },
      { key: "which", type: "seg", label: "Pages", value: "all", options: [["all", "All pages"], ["some", "Some pages"]] },
      { key: "pages", type: "text", label: "Which pages", value: "1", placeholder: "1, 3-4",
        when: (v) => v.which === "some" },
    ],
    async run({ files: [file], values }) {
      const { degrees } = await loadPdfLib();
      const doc = await openPdf(file);
      const pages = doc.getPages();
      const targets = values.which === "all" ? pages.map((_, i) => i) : parseRanges(values.pages, pages.length);
      for (const i of targets) {
        const page = pages[i];
        page.setRotation(degrees((page.getRotation().angle + Number(values.angle)) % 360));
      }
      return [{ blob: pdfBlob(await doc.save()), name: `${baseName(file.name)}-rotated.pdf` }];
    },
  },

  {
    id: "images-to-pdf",
    group: "pdf",
    icon: "image_editor",
    name: "Images to PDF",
    blurb: "Put photos or scans into one PDF, one image per page.",
    accept: "image/*",
    multiple: true,
    reorder: true,
    action: "Make PDF",
    fields: [
      { key: "size", type: "seg", label: "Page size", value: "fit",
        options: [["fit", "Fit each image"], ["a4", "A4"], ["letter", "Letter"]] },
    ],
    async run({ files, values, progress }) {
      const { PDFDocument } = await loadPdfLib();
      const out = await PDFDocument.create();
      const sizes = { a4: [595.28, 841.89], letter: [612, 792] };
      for (const [i, file] of files.entries()) {
        const bytes = await toPdfImageBytes(file);
        const img = bytes.kind === "jpg" ? await out.embedJpg(bytes.data) : await out.embedPng(bytes.data);
        if (values.size === "fit") {
          out.addPage([img.width, img.height]).drawImage(img, { x: 0, y: 0, width: img.width, height: img.height });
        } else {
          let [pw, ph] = sizes[values.size];
          if (img.width > img.height) [pw, ph] = [ph, pw];
          const margin = 24;
          const scale = Math.min((pw - margin * 2) / img.width, (ph - margin * 2) / img.height, 1);
          const w = img.width * scale, hgt = img.height * scale;
          out.addPage([pw, ph]).drawImage(img, { x: (pw - w) / 2, y: (ph - hgt) / 2, width: w, height: hgt });
        }
        progress((i + 1) / files.length);
      }
      return [{ blob: pdfBlob(await out.save()), name: `${baseName(files[0].name)}.pdf` }];
    },
  },

  {
    id: "pdf-to-images",
    group: "pdf",
    icon: "image_editor",
    name: "PDF to images",
    blurb: "Save each page of a PDF as a PNG or JPG picture.",
    accept: PDF,
    action: "Convert",
    fields: [
      { key: "format", type: "seg", label: "Format", value: "png", options: [["png", "PNG"], ["jpg", "JPG"]] },
      { key: "dpi", type: "seg", label: "Quality", value: "150",
        options: [["96", "Screen"], ["150", "Standard"], ["300", "Print"]] },
    ],
    async run({ files: [file], values, progress }) {
      const pdfjs = await loadPdfJs();
      const doc = await pdfjs.getDocument({ data: new Uint8Array(await file.arrayBuffer()) }).promise;
      const results = [];
      const scale = Number(values.dpi) / 72;
      const type = values.format === "png" ? "image/png" : "image/jpeg";
      for (let n = 1; n <= doc.numPages; n++) {
        const page = await doc.getPage(n);
        const viewport = page.getViewport({ scale });
        const canvas = document.createElement("canvas");
        canvas.width = Math.ceil(viewport.width);
        canvas.height = Math.ceil(viewport.height);
        const ctx = canvas.getContext("2d");
        if (type === "image/jpeg") { ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, canvas.width, canvas.height); }
        await page.render({ canvasContext: ctx, viewport }).promise;
        const blob = await new Promise((res) => canvas.toBlob(res, type, 0.92));
        results.push({ blob, name: `${baseName(file.name)}-page-${n}.${values.format}` });
        progress(n / doc.numPages);
        page.cleanup();
      }
      await doc.destroy();
      return results;
    },
  },
];

/** pdf-lib embeds only JPG and PNG; anything else goes through a canvas. */
async function toPdfImageBytes(file) {
  if (file.type === "image/jpeg") return { kind: "jpg", data: await file.arrayBuffer() };
  if (file.type === "image/png") return { kind: "png", data: await file.arrayBuffer() };
  const bitmap = await createImageBitmap(file);
  const canvas = new OffscreenCanvas(bitmap.width, bitmap.height);
  canvas.getContext("2d").drawImage(bitmap, 0, 0);
  const blob = await canvas.convertToBlob({ type: "image/png" });
  return { kind: "png", data: await blob.arrayBuffer() };
}
