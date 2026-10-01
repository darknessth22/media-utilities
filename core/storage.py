"""What Videl has stored on disk, and removing it.

Videl's AI tools download models and runtimes on demand, and on a machine
that has tried a few of them that is tens of gigabytes — measured at 25 GB on
one install, more than ten times the whole of %TEMP%. Nothing else in the app
shows it, so this module lists every item with its size and what uses it, and
removes the ones the user picks.

Safety, because this deletes things:

* **Only known items.** The list is built from the component registry and the
  Whisper model list, plus a fixed set of leftovers. Nothing is ever "every
  file in the folder": that folder also holds the licence/trial state and the
  browser-extension token, which must survive.
* **Only inside Videl's own folders.** Every removal is checked against the
  data folder and Videl's temp folder before anything is deleted (see
  :func:`_inside_allowed_root`).
* **Nothing shared.** ``~/.cache/huggingface`` and ``~/.cache/torch`` are not
  listed: other software on the machine uses them too.
* **No half-states.** Removing something other tools depend on removes those
  tools as well, so none of them is left installed-but-broken.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field

KIND_AI = "ai"
KIND_TRANSCRIPT = "transcript"
KIND_LEFTOVER = "leftover"


@dataclass
class StorageItem:
    id: str
    kind: str
    name_key: str           # i18n key for the item's name ("" -> use label)
    path: str
    label: str = ""         # literal name, for things like Whisper model names
    used_by: list[str] = field(default_factory=list)    # i18n keys of tools
    note_key: str = ""      # i18n key: what removing it means
    size: int = 0
    # Other item ids removed along with this one (dependents).
    cascade: list[str] = field(default_factory=list)


# ── Discovery ─────────────────────────────────────────────────────────────────

def _data_root() -> str:
    from utils.paths import user_data_dir

    return str(user_data_dir())


def _temp_root() -> str:
    return os.path.join(tempfile.gettempdir(), "videl_vupscale")


def size_of(path: str) -> int:
    """Bytes under *path*. Never follows links out of the tree."""
    if os.path.isfile(path):
        try:
            return os.path.getsize(path)
        except OSError:
            return 0
    # scandir, not os.walk + lstat: on Windows each DirEntry already carries
    # its size from the directory listing, so this is one system call per
    # FOLDER instead of one per file. torch_runtime alone is tens of thousands
    # of files, and the per-file version took over 40 s inside the running app.
    total = 0
    stack = [path]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                        elif not entry.is_symlink():
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


# Tools that use each AI component, beyond the component itself. The video
# upscaler has no component of its own: it runs on the image upscaler's.
_EXTRA_USERS = {
    "upscaler": ["tool_video_upscaler_name"],
    "ocr_rapid": ["storage_used_text_extractor", "tool_pdf_toolkit_name"],
    "ocr_easy": ["storage_used_text_extractor", "tool_pdf_toolkit_name"],
}

# The OCR components are named after their engine; what people know is the
# feature, so the storage page names that instead.
_NAME_OVERRIDES = {
    "ocr_rapid": "storage_ocr_rapid",
    "ocr_easy": "storage_ocr_easy",
}

def _dependents(component_id: str) -> list[str]:
    """Every component that needs *component_id*, directly or through another."""
    from core import ai_components

    found: list[str] = []
    frontier = [component_id]
    while frontier:
        current = frontier.pop()
        for cid in ai_components.all_ids():
            if current in ai_components.get(cid).requires and cid not in found:
                found.append(cid)
                frontier.append(cid)
    return found


def _whisper_name(label: str) -> str:
    """"large-v3  (f16, ~3.1 GB)" -> "Whisper large-v3 (f16)".

    The spec's label carries an estimated size, which would sit right next to
    the measured one and disagree with it.
    """
    name, _, rest = label.partition("  (")
    quality = rest.split(",")[0].rstrip(")").strip()
    return f"Whisper {name.strip()}" + (f" ({quality})" if quality else "")


def items(measure: bool = True) -> list[StorageItem]:
    """Everything Videl has stored that the user could remove.

    *measure* walks each item for its size — seconds on a big install, so the
    UI does it off the GUI thread.
    """
    from core import ai_components, transcript
    from utils import model_manager

    out: list[StorageItem] = []

    # AI components, including the hidden shared runtime: at 6 GB it is the
    # single largest thing Videl stores, and it had no remove button anywhere.
    for cid in ai_components.all_ids():
        path = model_manager._component_dir(cid)
        if not os.path.isdir(path):
            continue
        comp = ai_components.get(cid)
        # Only dependents that are actually installed: listing a tool the user
        # never installed as "using" the runtime is just wrong.
        dependents = [d for d in _dependents(cid)
                      if os.path.isdir(model_manager._component_dir(d))]
        # The item's own tool is not listed as its user — "AI Photo Restore,
        # used by AI Photo Restore" says nothing.
        users = list(_EXTRA_USERS.get(cid, []))
        for dep in dependents:
            users.append(ai_components.get(dep).label_key)
            users += _EXTRA_USERS.get(dep, [])
        out.append(StorageItem(
            id=f"ai:{cid}", kind=KIND_AI,
            name_key=_NAME_OVERRIDES.get(cid, comp.label_key), path=path,
            used_by=list(dict.fromkeys(users)),
            note_key="storage_note_reinstall",
            cascade=[f"ai:{d}" for d in dependents],
        ))

    # The LaMa inpainting model is a plain download, not a pip component.
    lama = os.path.join(_data_root(), "ai_packages", "inpaint")
    if os.path.isdir(lama):
        out.append(StorageItem(
            id="lama", kind=KIND_AI, name_key="storage_lama", path=lama,
            used_by=["tool_bg_eraser_name", "tool_photo_restore_name"],
            note_key="storage_note_redownload",
        ))

    # Whisper: each model file, and each installed engine.
    for spec in transcript.MODELS:
        path = os.path.join(transcript.models_dir(), spec.filename)
        if os.path.isfile(path):
            out.append(StorageItem(
                id=f"whisper_model:{spec.id}", kind=KIND_TRANSCRIPT,
                name_key="", label=_whisper_name(spec.label), path=path,
                used_by=["section_transcript"],
                note_key="storage_note_redownload",
            ))
    for backend in transcript.BACKENDS:
        path = transcript.backend_dir(backend.id)
        if os.path.isdir(path) and os.listdir(path):
            out.append(StorageItem(
                id=f"whisper_backend:{backend.id}", kind=KIND_TRANSCRIPT,
                name_key=f"storage_whisper_engine_{backend.id}", path=path,
                used_by=["section_transcript"],
                note_key="storage_note_reinstall",
            ))

    # Leftovers: safe to delete outright, nothing re-downloads.
    for item_id, key, parts in (
        ("pip_cache", "storage_pip_cache", ("ai_packages", "_pip_cache")),
        ("wheels", "storage_wheels", ("ai_packages", "_wheels")),
        ("update_staging", "storage_update_staging", ("update-staging",)),
    ):
        path = os.path.join(_data_root(), *parts)
        if os.path.isdir(path) and os.listdir(path):
            out.append(StorageItem(id=item_id, kind=KIND_LEFTOVER, name_key=key,
                                   path=path, note_key="storage_note_cache"))
    vup = _temp_root()
    if os.path.isdir(vup) and os.listdir(vup):
        out.append(StorageItem(
            id="video_upscale_frames", kind=KIND_LEFTOVER,
            name_key="storage_vupscale_frames", path=vup,
            used_by=["tool_video_upscaler_name"],
            note_key="storage_note_resume",
        ))

    if measure:
        for item in out:
            item.size = size_of(item.path)
    return out


# ── Removal ───────────────────────────────────────────────────────────────────

# Licence/trial state and the browser-extension pairing token live loose in the
# data folder. Deleting them would reset the trial or unpair the extension.
_PROTECTED_NAMES = frozenset({".trial", ".hwid", ".bridge_token"})


def _inside_allowed_root(path: str) -> bool:
    """True only for a path strictly inside Videl's data or temp folder.

    The last line of defence against a bad path: whatever the item list says,
    nothing outside these folders — never the folders themselves, and never
    the licence files that live loose inside the data folder — can be deleted
    from here.
    """
    try:
        real = os.path.normcase(os.path.realpath(path))
    except OSError:
        return False
    if os.path.basename(real) in _PROTECTED_NAMES:
        return False
    for root in (_data_root(), _temp_root()):
        base = os.path.normcase(os.path.realpath(root))
        if real != base and real.startswith(base + os.sep):
            return True
    return False


def is_busy(item: StorageItem) -> bool:
    """An AI component mid-install must not be deleted out from under pip.

    A stale "installing" state is rolled back at every launch, so during a
    session this flag reliably means an install is running right now.
    """
    if item.kind != KIND_AI or not item.id.startswith("ai:"):
        return False
    from utils import model_manager

    return model_manager.read_state(item.id[3:]).status == "installing"


def plan(item_id: str, catalogue: list[StorageItem]) -> list[StorageItem]:
    """The item and everything removed with it, in removal order."""
    by_id = {i.id: i for i in catalogue}
    order: list[StorageItem] = []
    pending = [item_id]
    while pending:
        current = pending.pop(0)
        item = by_id.get(current)
        if item is None or item in order:
            continue
        order.append(item)
        pending.extend(item.cascade)
    # Dependents first: never leave a tool pointing at a runtime that is gone.
    return list(reversed(order))


def remove(item: StorageItem) -> list[str]:
    """Delete one item. Returns paths that could not be removed (in use)."""
    if not _inside_allowed_root(item.path):
        raise PermissionError(f"Refusing to delete outside Videl's folders: {item.path}")
    if is_busy(item):
        raise RuntimeError("install in progress")

    if item.id.startswith("ai:"):
        from utils import model_manager

        return model_manager.uninstall(item.id[3:])
    if item.id.startswith("whisper_model:"):
        try:
            os.remove(item.path)
            return []
        except FileNotFoundError:
            return []
        except OSError:
            return [item.path]
    failed: list[str] = []
    if os.path.isdir(item.path):
        shutil.rmtree(item.path, onexc=lambda _fn, path, _exc: failed.append(path))
    elif os.path.exists(item.path):
        try:
            os.remove(item.path)
        except OSError:
            failed.append(item.path)
    return failed


def human_size(n: int) -> str:
    if n < 1024 ** 2:
        return f"{n / 1024:.0f} KB"
    if n < 1024 ** 3:
        return f"{n / 1024 ** 2:.0f} MB"
    return f"{n / 1024 ** 3:.1f} GB"
