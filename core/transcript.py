"""Local speech-to-text via whisper.cpp prebuilt binaries.

Ships no Python deps — instead downloads the official whisper.cpp release
zip from ggerganov/whisper.cpp (CPU or CUDA build) and shells out to
`whisper-cli.exe`. NVIDIA GPU acceleration when the CUDA backend is chosen.

Layout under %LOCALAPPDATA%\\Videl\\:
  whisper_bin\\{backend}\\whisper-cli.exe + ggml*.dll
  whisper_models\\ggml-*.bin

Pipeline: input media -> ffmpeg 16 kHz mono WAV -> whisper-cli -> SRT.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable, Optional

# whisper-cli `--print-progress` emits lines like
#   "whisper_print_progress_callback: progress = 12%"
# at ~1% granularity. Cheap to regex-match per line.
_PROGRESS_RE = re.compile(r"progress\s*=\s*(\d+)\s*%")

from utils.ffmpeg import ffmpeg_path
from utils.process_registry import tracked_run
from utils.gpu_detect import detect as _gpu_detect

_WIN_FLAGS = {"creationflags": 0x08000000} if sys.platform == "win32" else {}

_WHISPER_VERSION = "v1.8.4"
# Repo moved from `ggerganov/whisper.cpp` to `ggml-org/whisper.cpp` (still works
# via redirect, but pin the new path so future renames don't 302 us into 404).
_WHISPER_RELEASE_BASE = (
    "https://github.com/ggml-org/whisper.cpp/releases/download/"
    + _WHISPER_VERSION + "/"
)


@dataclass(frozen=True)
class WhisperBackend:
    id: str           # "cpu" | "cuda"
    label: str        # human label
    zip_name: str     # filename inside release
    size_mb: int      # approx download
    requires_nvidia: bool

    @property
    def url(self) -> str:
        return _WHISPER_RELEASE_BASE + self.zip_name


BACKENDS: list[WhisperBackend] = [
    WhisperBackend(
        id="cpu",
        label="CPU + BLAS (works on every machine, ~15 MB)",
        zip_name="whisper-blas-bin-x64.zip",
        size_mb=15,
        requires_nvidia=False,
    ),
    WhisperBackend(
        id="cuda",
        label="NVIDIA CUDA 12.4 (10–20× faster on RTX, ~435 MB)",
        zip_name="whisper-cublas-12.4.0-bin-x64.zip",
        size_mb=435,
        requires_nvidia=True,
    ),
]
BACKEND_BY_ID = {b.id: b for b in BACKENDS}


@dataclass(frozen=True)
class WhisperModelSpec:
    id: str
    filename: str
    size_mb: int
    label: str

    @property
    def url(self) -> str:
        return (
            "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
            + self.filename
        )


# Multilingual GGUF models. Q5_0 = quantized (~⅓ size, tiny accuracy loss).
MODELS: list[WhisperModelSpec] = [
    WhisperModelSpec("tiny-q5_0",            "ggml-tiny-q5_0.bin",             32,   "tiny  (Q5_0, ~32 MB)"),
    WhisperModelSpec("tiny",                 "ggml-tiny.bin",                  77,   "tiny  (f16, ~77 MB)"),
    WhisperModelSpec("base-q5_0",            "ggml-base-q5_0.bin",             60,   "base  (Q5_0, ~60 MB)"),
    WhisperModelSpec("base",                 "ggml-base.bin",                 148,   "base  (f16, ~148 MB)"),
    WhisperModelSpec("small-q5_0",           "ggml-small-q5_0.bin",           190,   "small  (Q5_0, ~190 MB)"),
    WhisperModelSpec("small",                "ggml-small.bin",                488,   "small  (f16, ~488 MB)"),
    WhisperModelSpec("medium-q5_0",          "ggml-medium-q5_0.bin",          539,   "medium  (Q5_0, ~540 MB)"),
    WhisperModelSpec("medium",               "ggml-medium.bin",              1530,   "medium  (f16, ~1.5 GB)"),
    WhisperModelSpec("large-v3-turbo-q5_0",  "ggml-large-v3-turbo-q5_0.bin",  574,   "large-v3-turbo  (Q5_0, ~570 MB)"),
    WhisperModelSpec("large-v3-turbo",       "ggml-large-v3-turbo.bin",      1624,   "large-v3-turbo  (f16, ~1.6 GB)"),
    WhisperModelSpec("large-v3-q5_0",        "ggml-large-v3-q5_0.bin",       1080,   "large-v3  (Q5_0, ~1.1 GB)"),
    WhisperModelSpec("large-v3",             "ggml-large-v3.bin",            3094,   "large-v3  (f16, ~3.1 GB)"),
]
MODEL_BY_ID = {m.id: m for m in MODELS}
DEFAULT_MODEL_ID = "medium-q5_0"
DEFAULT_BACKEND_ID = "cpu"

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}
VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv"}
INPUT_EXTS = AUDIO_EXTS | VIDEO_EXTS

LANGUAGES = [("auto", None), ("en", "en"), ("ar", "ar")]


@dataclass
class TranscriptResult:
    output_path: str
    language: str
    segment_count: int
    model_id: str
    backend_id: str


# ── Filesystem layout ──────────────────────────────────────────────────────
def _videl_root() -> str:
    from utils.paths import user_data_dir
    return str(user_data_dir())


def bin_root() -> str:
    d = os.path.join(_videl_root(), "whisper_bin")
    os.makedirs(d, exist_ok=True)
    return d


def backend_dir(backend_id: str) -> str:
    return os.path.join(bin_root(), backend_id)


def models_dir() -> str:
    d = os.path.join(_videl_root(), "whisper_models")
    os.makedirs(d, exist_ok=True)
    return d


def model_path(model_id: str) -> str:
    return os.path.join(models_dir(), MODEL_BY_ID[model_id].filename)


def _whisper_cli_path(backend_id: str) -> Optional[str]:
    """Find the whisper CLI exe inside an installed backend dir.

    Releases have varied between `main.exe` and `whisper-cli.exe` over time.
    """
    d = backend_dir(backend_id)
    if not os.path.isdir(d):
        return None
    for name in ("whisper-cli.exe", "main.exe", "whisper-cli", "main"):
        p = os.path.join(d, name)
        if os.path.isfile(p):
            return p
    # Recurse one level — some zips extract into a subdir.
    try:
        for entry in os.listdir(d):
            sub = os.path.join(d, entry)
            if not os.path.isdir(sub):
                continue
            for name in ("whisper-cli.exe", "main.exe", "whisper-cli", "main"):
                p = os.path.join(sub, name)
                if os.path.isfile(p):
                    return p
    except OSError:
        pass
    return None


# ── Backend install ────────────────────────────────────────────────────────
def is_backend_installed(backend_id: str) -> bool:
    return _whisper_cli_path(backend_id) is not None


def installed_backends() -> list[str]:
    return [b.id for b in BACKENDS if is_backend_installed(b.id)]


def recommended_backend() -> str:
    """CUDA if NVIDIA detected, else CPU."""
    return "cuda" if _gpu_detect() == "cuda" else "cpu"


def _download_to(url: str, dst: str,
                 progress_cb: Optional[Callable[[int, int], None]],
                 cancel_check: Optional[Callable[[], bool]]) -> None:
    tmp = dst + ".part"
    if os.path.isfile(tmp):
        os.remove(tmp)
    req = urllib.request.Request(url, headers={"User-Agent": "Videl/1.0"})
    try:
        resp_cm = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Download failed: HTTP {exc.code} for {url}") from exc
    with resp_cm as resp, open(tmp, "wb") as f:
        if getattr(resp, "status", 200) >= 400:
            raise RuntimeError(f"Download failed: HTTP {resp.status} for {url}")
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        chunk = 1024 * 256
        while True:
            if cancel_check and cancel_check():
                f.close()
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                raise RuntimeError("Download cancelled.")
            buf = resp.read(chunk)
            if not buf:
                break
            f.write(buf)
            done += len(buf)
            if progress_cb and total:
                try:
                    progress_cb(done, total)
                except Exception:
                    pass
    os.replace(tmp, dst)


def download_backend(
    backend_id: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    """Download + extract a whisper.cpp release zip. Returns backend dir."""
    if backend_id not in BACKEND_BY_ID:
        raise ValueError(f"Unknown backend: {backend_id}")
    target = backend_dir(backend_id)
    if is_backend_installed(backend_id):
        return target

    b = BACKEND_BY_ID[backend_id]
    # Nuke any stale partial install before extracting — leftovers from a
    # previous failed run (e.g. empty dir, mismatched DLLs) cause silent
    # "installed but doesn't work" state.
    if os.path.isdir(target):
        shutil.rmtree(target, ignore_errors=True)
    os.makedirs(target, exist_ok=True)

    # Download zip to temp.
    fd, zip_path = tempfile.mkstemp(prefix=f"videl_{backend_id}_", suffix=".zip")
    os.close(fd)
    try:
        _download_to(b.url, zip_path, progress_cb, cancel_check)
        if cancel_check and cancel_check():
            raise RuntimeError("Cancelled.")
        # Sanity-check the file before extracting: GitHub 404 returns an HTML
        # error page (~1 KB) with no zip magic.
        if os.path.getsize(zip_path) < 50_000:
            with open(zip_path, "rb") as f:
                head = f.read(64)
            if not head.startswith(b"PK"):
                raise RuntimeError(
                    f"Downloaded asset is not a zip (got {len(head)}-byte preview "
                    f"starting {head[:16]!r}). The release URL likely returned an "
                    f"error page — check {b.url}."
                )
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target)
    except Exception:
        # Wipe partial dir on any failure so the UI sees `installed=False` and
        # the user can retry cleanly.
        shutil.rmtree(target, ignore_errors=True)
        raise
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass

    if not is_backend_installed(backend_id):
        shutil.rmtree(target, ignore_errors=True)
        raise RuntimeError(
            f"whisper.cpp release {_WHISPER_VERSION} extracted but whisper-cli/main "
            f"executable was not found in {target}. Asset layout may have changed."
        )
    return target


def delete_backend(backend_id: str) -> None:
    d = backend_dir(backend_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)


# ── Model install ──────────────────────────────────────────────────────────
def is_model_downloaded(model_id: str) -> bool:
    if model_id not in MODEL_BY_ID:
        return False
    p = model_path(model_id)
    if not os.path.isfile(p):
        return False
    min_bytes = int(MODEL_BY_ID[model_id].size_mb * 1024 * 1024 * 0.7)
    return os.path.getsize(p) >= min_bytes


def installed_model_ids() -> list[str]:
    return [m.id for m in MODELS if is_model_downloaded(m.id)]


def download_model(
    model_id: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> str:
    if model_id not in MODEL_BY_ID:
        raise ValueError(f"Unknown model id: {model_id}")
    final = model_path(model_id)
    if is_model_downloaded(model_id):
        return final
    _download_to(MODEL_BY_ID[model_id].url, final, progress_cb, cancel_check)
    return final


def delete_model(model_id: str) -> None:
    p = model_path(model_id)
    if os.path.isfile(p):
        os.remove(p)


# ── Audio prep ─────────────────────────────────────────────────────────────
def _extract_wav(input_path: str) -> str:
    fd, wav_path = tempfile.mkstemp(prefix="videl_whisper_", suffix=".wav")
    os.close(fd)
    cmd = [
        ffmpeg_path, "-y",
        "-i", input_path,
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        wav_path,
    ]
    proc = tracked_run(
        cmd, str(uuid.uuid4()),
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=3600, **_WIN_FLAGS,
    )
    if proc.returncode != 0:
        try:
            os.remove(wav_path)
        except OSError:
            pass
        raise RuntimeError(f"ffmpeg audio extract failed: {(proc.stderr or '')[-1500:]}")
    return wav_path


# ── Transcribe ─────────────────────────────────────────────────────────────
def transcribe(
    input_path: str,
    *,
    backend_id: str = DEFAULT_BACKEND_ID,
    model_id: str = DEFAULT_MODEL_ID,
    language: str = "auto",
    translate: bool = False,
    output_path: Optional[str] = None,
    progress_cb: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> TranscriptResult:
    """Transcribe input media to SRT via whisper-cli.

    backend_id: "cpu" | "cuda".
    language: "auto" | "en" | "ar" | any Whisper code.
    translate: True -> Whisper translate task (English out). False (default) ->
               source language preserved (AR audio -> AR text).
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)
    if backend_id not in BACKEND_BY_ID:
        raise ValueError(f"Unknown backend: {backend_id}")
    if model_id not in MODEL_BY_ID:
        raise ValueError(f"Unknown model id: {model_id}")

    download_backend(backend_id, progress_cb=progress_cb, cancel_check=cancel_check)
    if cancel_check and cancel_check():
        raise RuntimeError("Cancelled.")
    download_model(model_id, progress_cb=progress_cb, cancel_check=cancel_check)
    if cancel_check and cancel_check():
        raise RuntimeError("Cancelled.")

    cli = _whisper_cli_path(backend_id)
    if not cli:
        raise RuntimeError(f"whisper-cli not found for backend {backend_id}.")

    lang_code = dict(LANGUAGES).get(language, language if language != "auto" else None)

    wav_path = _extract_wav(input_path)
    # Write whisper-cli output to a temp path with ASCII-only name. The user's
    # actual output_path may contain full-width punctuation / unicode that the
    # CLI can't fwrite() to under Windows codepage rules. We move on success.
    tmp_dir = tempfile.mkdtemp(prefix="videl_whisper_out_")
    tmp_stem = os.path.join(tmp_dir, "out")
    tmp_srt = tmp_stem + ".srt"
    try:
        if cancel_check and cancel_check():
            raise RuntimeError("Cancelled.")

        if output_path is None:
            base, _ = os.path.splitext(input_path)
            out_lang = "en" if translate else (lang_code or "auto")
            output_path = f"{base}.{out_lang}.srt"

        cmd = [
            cli,
            "-m", model_path(model_id),
            "-f", wav_path,
            "-osrt",
            "-of", tmp_stem,
            "--print-progress",   # forces "progress = N%" lines on stdout
            # Disable context carryover — the single biggest hallucination /
            # repetition-loop preventer. Other thresholds left at whisper.cpp
            # defaults: loosening them helps recall on Arabic but causes
            # English to loop on silent/musical segments.
            "-mc", "0",
        ]
        # Omit -l when auto-detecting. whisper-cli auto-detects by default;
        # passing "auto" works on most builds but `-l <lang>` is more reliable
        # only when a real code is given.
        if lang_code:
            cmd += ["-l", lang_code]
        if translate:
            cmd.append("--translate")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=os.path.dirname(cli),
            **_WIN_FLAGS,
        )

        # Non-blocking stdout drain via dedicated reader thread + Queue. The
        # poll loop below then checks cancel_check() every 100 ms regardless
        # of whether whisper-cli is talking — a blocking readline() would
        # freeze the cancel response during long silent processing windows.
        q: Queue = Queue()

        def _enqueue(stream, sink: Queue) -> None:
            try:
                for line in iter(stream.readline, ""):
                    sink.put(line)
            finally:
                try:
                    stream.close()
                except Exception:
                    pass

        reader = threading.Thread(target=_enqueue, args=(proc.stdout, q), daemon=True)
        reader.start()

        tail: list[str] = []
        last_pct = -1
        try:
            while True:
                if cancel_check and cancel_check():
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    raise RuntimeError("Cancelled.")
                try:
                    line = q.get(timeout=0.1)
                except Empty:
                    if proc.poll() is not None and q.empty():
                        break
                    continue
                line = line.rstrip()
                tail.append(line)
                if len(tail) > 200:
                    tail = tail[-200:]
                if progress_cb:
                    m = _PROGRESS_RE.search(line)
                    if m:
                        pct = int(m.group(1))
                        # De-dupe — whisper-cli sometimes prints same % twice.
                        if pct != last_pct:
                            last_pct = pct
                            try:
                                progress_cb(pct, 100)
                            except Exception:
                                pass
        finally:
            if proc.poll() is None:
                proc.wait()
            reader.join(timeout=2)

        if proc.returncode != 0:
            raise RuntimeError(
                f"whisper-cli exited {proc.returncode}.\n--- last output ---\n"
                + "\n".join(tail[-40:])
            )

        if not os.path.isfile(tmp_srt):
            raise RuntimeError(
                "whisper-cli reported success but no SRT file was written.\n"
                + "--- last output ---\n" + "\n".join(tail[-40:])
            )

        # Ensure target dir exists, then move temp SRT into place.
        out_dir = os.path.dirname(output_path) or "."
        os.makedirs(out_dir, exist_ok=True)
        if os.path.isfile(output_path):
            os.remove(output_path)
        shutil.move(tmp_srt, output_path)

        # Count SRT segments for the result label.
        n = 0
        with open(output_path, encoding="utf-8") as f:
            for line in f:
                if line.strip().isdigit():
                    n += 1

        detected = "en" if translate else (lang_code or "auto")
        return TranscriptResult(
            output_path=output_path,
            language=detected,
            segment_count=n,
            model_id=model_id,
            backend_id=backend_id,
        )
    finally:
        try:
            os.remove(wav_path)
        except OSError:
            pass
        shutil.rmtree(tmp_dir, ignore_errors=True)
