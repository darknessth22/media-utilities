"""Rule-based folder watcher — "if this lands here, do that".

Downloads folders turn into graveyards because tidying them is manual. This
runs the tidying: a rule names a folder to watch, conditions a file must meet,
and one action to take.

Two things make this safe enough to run unattended, and they are not optional:

* **Nothing is destructive.** ``delete`` sends to the Recycle Bin via the
  Windows shell, never ``os.remove``. A rule you got wrong is recoverable.
* **Every action is logged.** :func:`undo_last` reads the log back and puts
  files where they came from. Without it, a bad rule at 2am is unrecoverable
  and you cannot even tell what it touched.

Rules are OFF by default and each rule has its own enable flag, because the
worst case here is not a stale search result — it is a folder emptied into the
wrong place. :func:`preview` answers "what would this do" without doing it.
"""
from __future__ import annotations

import fnmatch
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass, asdict, field

_IS_WINDOWS = sys.platform == "win32"

# Extensions browsers use for a download still in flight. Acting on one of
# these moves a half-written file and corrupts it.
PARTIAL_EXTS = frozenset({
    ".crdownload", ".part", ".partial", ".download", ".!ut", ".opdownload",
})

ACTIONS = ("move", "copy", "delete", "strip_exif")

# Named groups, so a rule can say "images" instead of making someone type
# "*.jpg, *.jpeg, *.png, *.webp, ...". Stored on the rule by KEY, not expanded,
# so adding a format here upgrades every existing rule.
FILE_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "images": ("Images", (
        ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif",
        ".heic", ".heif", ".svg", ".ico", ".avif",
    )),
    "video": ("Videos", (
        ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".m4v", ".wmv",
        ".mpg", ".mpeg", ".3gp", ".ts",
    )),
    "audio": ("Audio", (
        ".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".wma", ".opus",
        ".aiff", ".mid",
    )),
    "documents": ("Documents", (
        ".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx",
        ".ppt", ".pptx", ".csv", ".md", ".epub",
    )),
    "archives": ("Archives", (
        ".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso",
    )),
    "installers": ("Installers", (
        ".exe", ".msi", ".appx", ".msix", ".bat", ".cmd",
    )),
    "code": ("Code", (
        ".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yml",
        ".yaml", ".c", ".cpp", ".h", ".java", ".rs", ".go", ".sh",
    )),
}


def group_extensions(keys) -> set[str]:
    """Every extension covered by the named groups in *keys*."""
    out: set[str] = set()
    for key in keys or ():
        entry = FILE_GROUPS.get(key)
        if entry:
            out.update(entry[1])
    return out

_LOG_NAME = "folder_rules_log.jsonl"
_LOG_LIMIT = 2000           # entries kept; older ones age out


# ── Model ─────────────────────────────────────────────────────────────────────

@dataclass
class Rule:
    """One if-this-then-that rule.

    Conditions are ANDed. An empty condition means "don't care", so a rule with
    only ``folder`` and ``action`` matches everything in that folder — which is
    why :func:`preview` exists.
    """
    name: str = ""
    folder: str = ""                # watched directory
    enabled: bool = False           # per-rule switch; off until asked for
    # Named file-type groups, e.g. ["images", "documents"]. Stored by key so a
    # format added to FILE_GROUPS later applies to rules already saved.
    groups: list = field(default_factory=list)
    patterns: list = field(default_factory=list)   # ["*.pdf", "invoice*"]
    min_size: int = 0               # bytes, 0 = no minimum
    max_size: int = 0               # bytes, 0 = no maximum
    older_than_days: int = 0        # 0 = any age
    action: str = "move"
    destination: str = ""           # for move/copy
    include_subfolders: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Rule":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass(frozen=True)
class Action:
    """What a rule would do, or did, to one file."""
    rule: str
    action: str
    source: str
    destination: str = ""
    error: str = ""


def is_valid(rule: Rule) -> str:
    """Return an error message, or "" when the rule is usable."""
    if not (rule.name or "").strip():
        return "Rule needs a name"
    if not rule.folder or not os.path.isdir(rule.folder):
        return "Watched folder does not exist"
    if rule.action not in ACTIONS:
        return f"Unknown action: {rule.action}"
    if rule.action in ("move", "copy"):
        if not rule.destination:
            return "Move and copy need a destination folder"
        # Moving a folder into itself is an infinite tidy-loop.
        src = os.path.normcase(os.path.normpath(rule.folder))
        dst = os.path.normcase(os.path.normpath(rule.destination))
        if dst == src or dst.startswith(src + os.sep):
            return "Destination cannot be inside the watched folder"
    if rule.max_size and rule.min_size and rule.max_size < rule.min_size:
        return "Maximum size is below minimum size"
    return ""


# ── Matching ──────────────────────────────────────────────────────────────────

def matches(rule: Rule, path: str, *, now: float | None = None) -> bool:
    """Does one file satisfy every condition in *rule*?"""
    if not os.path.isfile(path):
        return False
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()

    # A download in flight is not a finished file, whatever the rule says.
    if ext in PARTIAL_EXTS:
        return False

    # Groups and patterns are ORed: ticking "Images" and typing "invoice*"
    # means images OR anything called invoice, which is what someone setting
    # both would expect. Neither set means "every file".
    if rule.groups or rule.patterns:
        low = name.lower()
        in_group = ext in group_extensions(rule.groups)
        hit_pattern = any(fnmatch.fnmatch(low, str(p).lower())
                          for p in rule.patterns)
        if not (in_group or hit_pattern):
            return False

    try:
        st = os.stat(path)
    except OSError:
        return False

    if rule.min_size and st.st_size < rule.min_size:
        return False
    if rule.max_size and st.st_size > rule.max_size:
        return False
    if rule.older_than_days:
        cutoff = (now if now is not None else time.time()) - rule.older_than_days * 86400
        if st.st_mtime > cutoff:
            return False
    return True


def _candidates(rule: Rule) -> list[str]:
    """Files in the watched folder, honouring include_subfolders."""
    found: list[str] = []
    if not rule.folder or not os.path.isdir(rule.folder):
        return found
    if rule.include_subfolders:
        for root, dirs, files in os.walk(rule.folder):
            dirs[:] = [d for d in dirs if not d.startswith("$")]
            found.extend(os.path.join(root, f) for f in files)
    else:
        try:
            with os.scandir(rule.folder) as it:
                for entry in it:
                    try:
                        if entry.is_file(follow_symlinks=False):
                            found.append(entry.path)
                    except OSError:
                        continue
        except (PermissionError, OSError):
            return found
    return found


def preview(rules: list[Rule]) -> list[Action]:
    """What *would* happen. Touches nothing on disk.

    This is the dry run — the difference between a rule engine you can trust
    and one you find out about afterwards.
    """
    planned: list[Action] = []
    for rule in rules:
        if not rule.enabled or is_valid(rule):
            continue
        for path in _candidates(rule):
            if not matches(rule, path):
                continue
            dest = ""
            if rule.action in ("move", "copy"):
                dest = _free_name(os.path.join(rule.destination,
                                               os.path.basename(path)))
            planned.append(Action(rule.name, rule.action, path, dest))
    return planned


# ── Doing it ──────────────────────────────────────────────────────────────────

def _free_name(target: str) -> str:
    """A path that does not exist yet — never silently overwrite."""
    if not os.path.exists(target):
        return target
    stem, ext = os.path.splitext(target)
    for n in range(1, 1000):
        candidate = f"{stem} ({n}){ext}"
        if not os.path.exists(candidate):
            return candidate
    return f"{stem} ({int(time.time())}){ext}"


def recycle(path: str) -> None:
    """Send to the Recycle Bin. Raises OSError if the shell refuses.

    ``os.remove`` is deliberately not the fallback: an unrecoverable delete
    driven by a rule the user mistyped is the worst outcome this module has.
    """
    if not _IS_WINDOWS:
        raise OSError("Recycle Bin is only available on Windows")
    import ctypes
    from ctypes import wintypes

    FO_DELETE = 0x0003
    FOF_ALLOWUNDO = 0x0040
    FOF_NOCONFIRMATION = 0x0010
    FOF_NOERRORUI = 0x0400
    FOF_SILENT = 0x0004

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", ctypes.c_uint16),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", ctypes.c_void_p),
            ("lpszProgressTitle", wintypes.LPCWSTR),
        ]

    # pFrom is a double-NUL-terminated list; one trailing NUL is not enough.
    op = SHFILEOPSTRUCTW(
        None, FO_DELETE, os.path.abspath(path) + "\0\0", None,
        FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT,
        False, None, None,
    )
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if rc != 0:
        raise OSError(f"Recycle Bin refused (code {rc}): {path}")


def strip_exif(path: str) -> None:
    """Rewrite an image without its metadata, preserving orientation.

    Orientation is applied to the pixels first: dropping the EXIF tag without
    that turns every phone photo sideways.
    """
    from PIL import Image, ImageOps

    with Image.open(path) as im:
        # Read the format BEFORE transposing: exif_transpose returns a new
        # image whose .format is None, and format=None writes a file Pillow
        # itself cannot read back.
        fmt = (im.format or "").upper()
        if not fmt:
            raise OSError(f"Unrecognised image format: {path}")
        fixed = ImageOps.exif_transpose(im)
        # A fresh image carries no info dict, so no EXIF/XMP/IPTC rides along.
        clean = Image.new(fixed.mode, fixed.size)
        clean.paste(fixed)
        params = {}
        if fmt in ("JPEG", "JPG"):
            # No subsampling="keep" here: it needs a decoded JPEG as the
            # source, and `clean` is a new image, so Pillow raises — after
            # truncating the file it had already opened for writing.
            params = {"quality": 95}

    # Write beside the original and swap, so a save that fails part-way leaves
    # the original intact rather than a zero-byte file.
    tmp = f"{path}.videl-tmp"
    try:
        clean.save(tmp, format=fmt, **params)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def apply(rules: list[Rule], *, log: bool = True) -> list[Action]:
    """Run the rules for real. Returns what was done, errors included."""
    done: list[Action] = []
    for planned in preview(rules):
        try:
            if planned.action == "move":
                os.makedirs(os.path.dirname(planned.destination), exist_ok=True)
                # Re-resolve: an earlier action this pass may have taken the name.
                target = _free_name(planned.destination)
                shutil.move(planned.source, target)
                planned = Action(planned.rule, "move", planned.source, target)
            elif planned.action == "copy":
                os.makedirs(os.path.dirname(planned.destination), exist_ok=True)
                target = _free_name(planned.destination)
                shutil.copy2(planned.source, target)
                planned = Action(planned.rule, "copy", planned.source, target)
            elif planned.action == "delete":
                recycle(planned.source)
            elif planned.action == "strip_exif":
                strip_exif(planned.source)
        except Exception as exc:               # noqa: BLE001 - reported, not raised
            done.append(Action(planned.rule, planned.action, planned.source,
                               planned.destination, str(exc)))
            continue
        done.append(planned)
        if log:
            _append_log(planned)
    return done


# ── Undo log ──────────────────────────────────────────────────────────────────

def log_path() -> str:
    from core.settings import SettingsManager

    folder = os.path.dirname(str(SettingsManager.get_config_path()))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, _LOG_NAME)


def _append_log(action: Action) -> None:
    try:
        with open(log_path(), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**asdict(action), "at": time.time()}) + "\n")
    except OSError:
        pass        # a failed log must never break the action itself


def history(limit: int = 200) -> list[dict]:
    """Most recent actions first."""
    try:
        with open(log_path(), "r", encoding="utf-8") as fh:
            lines = fh.readlines()[-_LOG_LIMIT:]
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out


def undo_last(count: int = 1) -> list[str]:
    """Put the last *count* moved/copied files back. Returns what was undone.

    Only ``move`` and ``copy`` are reversible here. A recycled file is restored
    from the Recycle Bin by the user; EXIF data that was stripped is gone.
    """
    entries = history(limit=count)
    undone: list[str] = []
    consumed = 0
    for entry in entries:
        action = entry.get("action")
        src = entry.get("source")
        dst = entry.get("destination")
        if entry.get("error"):
            consumed += 1
            continue
        try:
            if action == "move" and dst and src and os.path.exists(dst):
                os.makedirs(os.path.dirname(src), exist_ok=True)
                shutil.move(dst, _free_name(src))
                undone.append(src)
            elif action == "copy" and dst and os.path.exists(dst):
                os.remove(dst)      # removing the copy we made, not the original
                undone.append(dst)
        except OSError:
            pass
        consumed += 1
    if consumed:
        _trim_log(consumed)
    return undone


def _trim_log(count: int) -> None:
    """Drop the last *count* entries, so undo does not replay them."""
    try:
        with open(log_path(), "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        keep = lines[:-count] if count < len(lines) else []
        with open(log_path(), "w", encoding="utf-8") as fh:
            fh.writelines(keep)
    except OSError:
        pass


# ── Persistence ───────────────────────────────────────────────────────────────

def load_rules(settings) -> list[Rule]:
    return [Rule.from_dict(d) for d in (getattr(settings, "folder_rules", None) or [])]


def save_rules(settings, rules: list[Rule]) -> None:
    settings.folder_rules = [r.to_dict() for r in rules]
