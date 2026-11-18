// Video and audio tools, all FFmpeg (ffmpeg.wasm) running in the tab.
import { runFFmpeg } from "../engines.js";
import { baseName, ext } from "../ui.js";

const MEDIA = "video/*,audio/*,.mkv,.mov,.avi,.flv,.wmv,.m4a,.flac,.opus";
const COPYABLE = new Set(["mp4", "mkv", "mov"]);

const FORMATS = {
  mp4: { type: "video/mp4", args: ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"] },
  webm: { type: "video/webm", args: ["-c:v", "libvpx", "-deadline", "realtime", "-cpu-used", "8", "-b:v", "2M", "-c:a", "libvorbis"] },
  mov: { type: "video/quicktime", args: ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k"] },
  mkv: { type: "video/x-matroska", args: ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "160k"] },
  mp3: { type: "audio/mpeg", args: ["-vn", "-c:a", "libmp3lame", "-b:a", "192k"] },
  m4a: { type: "audio/mp4", args: ["-vn", "-c:a", "aac", "-b:a", "192k"] },
  wav: { type: "audio/wav", args: ["-vn", "-c:a", "pcm_s16le"] },
  ogg: { type: "audio/ogg", args: ["-vn", "-c:a", "libvorbis", "-q:a", "5"] },
};

const inName = (file, i = 0) => `in${i}.${ext(file.name) || "bin"}`;
// Clockwise degrees, 0 to 359, from the Rotate field: a listed choice or a typed angle.
const turn = (v) => ({ none: 0, right: 90, left: 270, 180: 180 }[v] ?? ((Number(v) % 360) + 360) % 360);

export const videoTools = [
  {
    id: "convert",
    group: "video",
    icon: "convert",
    name: "Convert",
    blurb: "Change a video or audio file to another format, or pull the sound out as MP3.",
    accept: MEDIA,
    preview: "video",
    action: "Convert",
    fields: [
      { key: "format", type: "seg", label: "Convert to", value: "mp4",
        options: [["mp4", "MP4"], ["webm", "WebM"], ["mov", "MOV"], ["mkv", "MKV"], ["mp3", "MP3"], ["m4a", "M4A"], ["wav", "WAV"], ["ogg", "OGG"]] },
      { key: "method", type: "seg", label: "Method", value: "encode",
        options: [["encode", "Re-encode"], ["copy", "Copy streams"]],
        hint: "Copy streams is instant but only works when the codecs already fit the new container.",
        when: (v) => COPYABLE.has(v.format) },
    ],
    async run({ files: [file], values, progress, status, meta }) {
      const fmt = FORMATS[values.format];
      const codec = values.method === "copy" && COPYABLE.has(values.format) ? ["-c", "copy"] : fmt.args;
      const output = `out.${values.format}`;
      const blob = await runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-i", inName(file), ...codec, output],
        output, type: fmt.type, duration: meta.duration, onProgress: progress, onStatus: status,
      });
      return [{ blob, name: `${baseName(file.name)}.${values.format}` }];
    },
  },

  {
    id: "trim",
    group: "video",
    icon: "trim",
    name: "Trim",
    blurb: "Cut a clip out of a video or song by dragging the start and end handles.",
    accept: MEDIA,
    preview: "timeline",
    action: "Trim",
    fields: [
      { key: "method", type: "seg", label: "Cut", value: "copy",
        options: [["copy", "Fast"], ["precise", "Frame-exact"]],
        hint: "Fast cuts at the nearest keyframe and keeps the original quality. Frame-exact re-encodes the clip." },
    ],
    async run({ files: [file], values, progress, status, meta }) {
      const { start, end } = meta;
      const extension = ext(file.name) || "mp4";
      const precise = values.method === "precise";
      const output = `out.${precise ? "mp4" : extension}`;
      const codec = precise
        ? ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "160k"]
        : ["-c", "copy", "-avoid_negative_ts", "make_zero"];
      const blob = await runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-ss", String(start), "-to", String(end), "-i", inName(file), ...codec, output],
        output, type: precise ? "video/mp4" : file.type || "video/mp4",
        duration: end - start, onProgress: progress, onStatus: status,
      });
      return [{ blob, name: `${baseName(file.name)}-clip.${precise ? "mp4" : extension}` }];
    },
  },

  {
    id: "compress",
    group: "video",
    icon: "compress",
    name: "Compress",
    blurb: "Make a video smaller so it fits email or chat limits.",
    accept: "video/*,.mkv,.mov,.avi",
    preview: "video",
    action: "Compress",
    fields: [
      { key: "level", type: "seg", label: "Strength", value: "30",
        options: [["26", "Light"], ["30", "Balanced"], ["34", "Strong"]],
        hint: "Stronger means a smaller file and softer picture." },
      { key: "height", type: "seg", label: "Resolution", value: "keep",
        options: [["keep", "Keep"], ["1080", "1080p"], ["720", "720p"], ["480", "480p"]],
        custom: { value: "540", min: 144, max: 4320, unit: "p", whole: true } },
      { key: "audio", type: "seg", label: "Sound", value: "128k",
        options: [["128k", "Keep"], ["64k", "Smaller"], ["none", "Remove"]] },
    ],
    async run({ files: [file], values, progress, status, meta }) {
      const scale = values.height === "keep" ? [] : ["-vf", `scale=-2:'trunc(min(ih,${values.height})/2)*2'`];
      const audio = values.audio === "none" ? ["-an"] : ["-c:a", "aac", "-b:a", values.audio];
      const blob = await runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-i", inName(file), ...scale, "-c:v", "libx264", "-preset", "veryfast", "-crf", values.level, ...audio, "-movflags", "+faststart", "out.mp4"],
        output: "out.mp4", type: "video/mp4", duration: meta.duration, onProgress: progress, onStatus: status,
      });
      return [{ blob, name: `${baseName(file.name)}-small.mp4`, compareTo: file.size }];
    },
  },

  {
    id: "gif",
    group: "video",
    icon: "gif",
    name: "Make a GIF",
    blurb: "Turn a moment from a video into an animated GIF.",
    accept: "video/*,.mkv,.mov",
    preview: "timeline",
    maxClip: 15,
    action: "Make GIF",
    fields: [
      { key: "width", type: "seg", label: "Width", value: "480",
        options: [["320", "320 px"], ["480", "480 px"], ["640", "640 px"]],
        custom: { value: "400", min: 64, max: 1920, unit: "px", whole: true } },
      { key: "fps", type: "seg", label: "Smoothness", value: "12",
        options: [["8", "8 fps"], ["12", "12 fps"], ["20", "20 fps"]],
        custom: { value: "15", min: 1, max: 50, unit: "fps", whole: true },
        hint: "Wider and smoother GIFs get large fast. Keep clips under 15 seconds." },
    ],
    async run({ files: [file], values, progress, status, meta }) {
      const { start, end } = meta;
      const graph = `fps=${values.fps},scale=${values.width}:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=5`;
      const blob = await runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-ss", String(start), "-t", String(end - start), "-i", inName(file), "-filter_complex", graph, "-loop", "0", "out.gif"],
        output: "out.gif", type: "image/gif", duration: end - start, onProgress: progress, onStatus: status,
      });
      return [{ blob, name: `${baseName(file.name)}.gif` }];
    },
  },

  {
    id: "merge",
    group: "video",
    icon: "merge",
    name: "Merge videos",
    blurb: "Join several clips into one video, in the order you choose.",
    accept: "video/*,.mkv,.mov",
    multiple: true,
    minFiles: 2,
    reorder: true,
    preview: null,
    action: "Merge",
    fields: [
      { key: "mode", type: "seg", label: "Mode", value: "fast",
        options: [["fast", "Fast"], ["compatible", "Compatible"]],
        hint: "Fast joins clips from the same camera or app without re-encoding. Compatible re-encodes so clips of different sizes or formats join cleanly." },
    ],
    async run({ files, values, progress, status, meta }) {
      const inputs = files.map((file, i) => ({ name: inName(file, i), file }));
      const total = meta.durations.reduce((a, b) => a + b, 0);
      let args, extraFiles = [];
      if (values.mode === "fast") {
        const list = inputs.map((i) => `file '${i.name}'`).join("\n");
        extraFiles = [{ name: "list.txt", data: new TextEncoder().encode(list) }];
        args = ["-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "out.mp4"];
      } else {
        const { width = 1280, height = 720 } = meta;
        const w = width - (width % 2), hgt = height - (height % 2);
        const parts = inputs.map((_, i) =>
          `[${i}:v]scale=${w}:${hgt}:force_original_aspect_ratio=decrease,pad=${w}:${hgt}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v${i}];[${i}:a]aresample=48000[a${i}]`);
        const joins = inputs.map((_, i) => `[v${i}][a${i}]`).join("");
        args = [...inputs.flatMap((i) => ["-i", i.name]),
          "-filter_complex", `${parts.join(";")};${joins}concat=n=${inputs.length}:v=1:a=1[v][a]`,
          "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "out.mp4"];
      }
      const blob = await runFFmpeg({ inputs, extraFiles, args, output: "out.mp4", type: "video/mp4", duration: total, onProgress: progress, onStatus: status });
      return [{ blob, name: `${baseName(files[0].name)}-merged.mp4` }];
    },
  },

  {
    id: "mux",
    group: "video",
    icon: "mux",
    name: "Audio in video",
    blurb: "Remove the sound from a video, or replace it with another audio file.",
    accept: MEDIA,
    multiple: true,
    preview: null,
    action: "Apply",
    fields: [
      { key: "mode", type: "seg", label: "What to do", value: "remove",
        options: [["remove", "Remove sound"], ["replace", "Replace sound"], ["add", "Add a second track"]],
        hint: "Replace and add need a video plus one audio file." },
    ],
    validate(files, values) {
      const video = files.find((f) => f.type.startsWith("video/") || /\.(mkv|mov|avi)$/i.test(f.name));
      const audio = files.find((f) => f !== video && f.type.startsWith("audio/"));
      if (!video) return "Add a video file.";
      if (values.mode !== "remove" && !audio) return "Add an audio file to use with the video.";
      return null;
    },
    async run({ files, values, progress, status, meta }) {
      const video = files.find((f) => f.type.startsWith("video/") || /\.(mkv|mov|avi)$/i.test(f.name));
      const audio = files.find((f) => f !== video && f.type.startsWith("audio/"));
      const v = inName(video, 0);
      const extension = ext(video.name) || "mp4";
      const inputs = [{ name: v, file: video }];
      let args;
      if (values.mode === "remove") {
        args = ["-i", v, "-c", "copy", "-an", `out.${extension}`];
      } else {
        const a = inName(audio, 1);
        inputs.push({ name: a, file: audio });
        args = values.mode === "replace"
          ? ["-i", v, "-i", a, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", `out.${extension}`]
          : ["-i", v, "-i", a, "-map", "0", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", `out.${extension}`];
      }
      const blob = await runFFmpeg({ inputs, args, output: `out.${extension}`, type: video.type || "video/mp4", duration: meta.duration, onProgress: progress, onStatus: status });
      const suffix = { remove: "silent", replace: "new-audio", add: "two-tracks" }[values.mode];
      return [{ blob, name: `${baseName(video.name)}-${suffix}.${extension}` }];
    },
  },

  // Desktop: Auto-Chunker (core/chunker.py).
  {
    id: "split",
    group: "video",
    icon: "chunk",
    name: "Split video",
    blurb: "Cut a long video or recording into parts of a set length or file size, without re-encoding.",
    accept: MEDIA,
    preview: "video",
    action: "Split",
    fields: [
      { key: "by", type: "seg", label: "Split by", value: "length",
        options: [["length", "Length"], ["size", "File size"]] },
      { key: "length", type: "seg", label: "Each part", value: "60",
        options: [["30", "30 s"], ["60", "1 min"], ["300", "5 min"], ["600", "10 min"]],
        custom: { value: "45", min: 1, max: 86400, unit: "seconds" },
        hint: "Nothing is re-encoded, so each part ends at the next keyframe and can run a few seconds over.",
        when: (v) => v.by === "length" },
      { key: "size", type: "seg", label: "Each part under", value: "25",
        options: [["10", "10 MB"], ["25", "25 MB"], ["50", "50 MB"], ["100", "100 MB"]],
        custom: { value: "8", min: 1, max: 4000, unit: "MB" },
        hint: "Nothing is re-encoded, so the quality stays the same.",
        when: (v) => v.by === "size" },
    ],
    async run({ files: [file], values, progress, status, meta }) {
      const extension = ext(file.name) || "mp4";
      const output = `part%03d.${extension}`;
      const split = (seconds) => runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-i", inName(file), "-map", "0:v:0?", "-map", "0:a?", "-c", "copy", "-f", "segment",
          "-segment_time", String(seconds), "-reset_timestamps", "1", "-avoid_negative_ts", "make_zero", output],
        output, type: file.type || "video/mp4", duration: meta.duration, onProgress: progress, onStatus: status,
      });
      let parts;
      if (values.by === "length") parts = await split(Number(values.length));
      else {
        if (!meta.duration) throw new Error("This file's length couldn't be read, so it can't be split by size. Split it by length instead.");
        // Estimate each part's length from the average bitrate, then shorten it and
        // split again if a part still came out too big (the bitrate varies).
        const limit = Number(values.size) * 1e6;
        let seconds = Math.max(1, Math.floor(meta.duration * limit * 0.9 / file.size));
        for (let attempt = 1; ; attempt++) {
          parts = await split(seconds);
          const biggest = Math.max(...parts.map((b) => b.size));
          if (biggest <= limit || attempt === 3 || seconds === 1) break;
          seconds = Math.max(1, Math.floor(seconds * limit / biggest * 0.95));
        }
      }
      const digits = Math.max(2, String(parts.length).length);
      return parts.map((blob, i) => ({ blob, name: `${baseName(file.name)}-part${String(i + 1).padStart(digits, "0")}.${extension}` }));
    },
  },

  // Desktop: Transform Media (core/spatial.py).
  {
    id: "transform",
    group: "video",
    icon: "spatial",
    name: "Rotate, crop, resize",
    blurb: "Turn a sideways video upright, crop it to 9:16 or square, or make it smaller.",
    accept: "video/*,.mkv,.mov,.avi",
    preview: "video",
    action: "Apply",
    fields: [
      { key: "rotate", type: "seg", label: "Rotate", value: "none",
        options: [["none", "None"], ["right", "90° right"], ["left", "90° left"], ["180", "180°"]],
        custom: { value: "15", min: -359, max: 359, unit: "degrees, clockwise" },
        hint: "Angles other than 90, 180 and 270 tilt the picture and fill the corners with black." },
      { key: "mirror", type: "seg", label: "Mirror", value: "no",
        options: [["no", "No"], ["yes", "Flip left to right"]] },
      { key: "crop", type: "seg", label: "Crop to", value: "keep",
        options: [["keep", "Keep"], ["9:16", "9:16"], ["1:1", "1:1"], ["4:5", "4:5"], ["16:9", "16:9"]],
        custom: { value: "3:2", ratio: true },
        hint: "9:16 for Reels, TikTok and Shorts, 4:5 for Instagram posts, 16:9 for YouTube. The centre is kept, after rotating." },
      { key: "size", type: "seg", label: "Size", value: "keep",
        options: [["keep", "Keep"], ["1080", "1080p"], ["720", "720p"], ["480", "480p"]],
        custom: { value: "540", min: 16, max: 4320, unit: "p", whole: true },
        hint: "Measured on the shorter side, so a vertical 1080p video is 1080 by 1920. A smaller video is never enlarged." },
    ],
    validate(files, values) {
      const unchanged = !turn(values.rotate) && values.mirror === "no" && values.crop === "keep" && values.size === "keep";
      return unchanged ? "Choose at least one change: rotate, mirror, crop or size." : null;
    },
    async run({ files: [file], values, progress, status, meta }) {
      const filters = [];
      const angle = turn(values.rotate);
      if (angle === 90) filters.push("transpose=1");
      else if (angle === 270) filters.push("transpose=2");
      else if (angle === 180) filters.push("hflip,vflip");
      else if (angle) {   // any other angle: tilt, grow the frame to fit, black corners
        const r = `${angle}*PI/180`;
        filters.push(`rotate=${r}:ow=rotw(${r}):oh=roth(${r}):c=black`, "scale=trunc(iw/2)*2:trunc(ih/2)*2");
      }
      if (values.mirror === "yes") filters.push("hflip");
      if (values.crop !== "keep") {
        const [a, b] = values.crop.split(":");
        filters.push(`crop='trunc(min(iw,ih*${a}/${b})/2)*2':'trunc(min(ih,iw*${b}/${a})/2)*2'`);
      }
      if (values.size !== "keep") {
        const n = values.size;   // shorter side, never enlarged; -2 keeps the shape with even sizes
        filters.push(`scale='if(gte(iw,ih),-2,trunc(min(iw,${n})/2)*2)':'if(gte(iw,ih),trunc(min(ih,${n})/2)*2,-2)'`);
      }
      const blob = await runFFmpeg({
        inputs: [{ name: inName(file), file }],
        args: ["-i", inName(file), "-vf", filters.join(","), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "out.mp4"],
        output: "out.mp4", type: "video/mp4", duration: meta.duration, onProgress: progress, onStatus: status,
      });
      return [{ blob, name: `${baseName(file.name)}-edited.mp4` }];
    },
  },
];
