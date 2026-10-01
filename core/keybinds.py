"""User-customisable keyboard shortcuts.

Every shortcut in the app is declared once in :data:`ACTIONS`. The registry
owns the defaults, the user's overrides, validation and conflict detection;
``gui/app.py`` only supplies the handler for each action id.

Three things this has to get right:

* **One source of truth.** Shortcuts used to be hardcoded at their call site
  AND listed again in the title bar menu, so the two drifted — Ctrl+K was
  missing from the menu for a long time. The menu is now generated from here.
* **Conflicts must be caught.** Two QShortcuts on one sequence means one of
  them silently never fires, with no error anywhere.
* **A bad binding must not lock the user out.** Anything unparseable falls
  back to the default rather than leaving an action unreachable.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KeybindAction:
    """One rebindable action.

    id:       stable key used in config.json — never change it, it is what a
              user's saved override is stored against.
    default:  QKeySequence portable string ("Ctrl+K").
    label_key: i18n key for the description shown in the UI.
    group_key: i18n key for the section heading it is listed under.
    global_hotkey: registered with the OS as well, so it works while Videl is
              minimised. Costs an exclusive system-wide claim, so it is opt-in
              per action (see core/hotkey.py).
    """

    id: str
    default: str
    label_key: str
    group_key: str
    global_hotkey: bool = False


# Order here is the order shown in the shortcuts menu and the settings page.
ACTIONS: tuple[KeybindAction, ...] = (
    KeybindAction("primary_action", "Ctrl+Return", "sc_primary", "sc_group_general"),
    KeybindAction("cancel", "Esc", "sc_cancel", "sc_group_general"),
    KeybindAction("paste_url", "Ctrl+V", "sc_paste", "sc_group_general"),
    KeybindAction("quick_search", "Ctrl+K", "sc_search", "sc_group_general"),

    KeybindAction("go_home", "Ctrl+H", "sc_home", "sc_group_navigation"),
    KeybindAction("go_tools", "Ctrl+T", "sc_tools", "sc_group_navigation"),
    KeybindAction("open_settings", "Ctrl+,", "sc_settings", "sc_group_navigation"),
    KeybindAction("open_guide", "F1", "sc_guide", "sc_group_navigation"),
    KeybindAction("quit", "Ctrl+Q", "sc_quit", "sc_group_navigation"),

    KeybindAction("pick_color", "Ctrl+B", "sc_pick", "sc_group_tools"),
    KeybindAction("pick_color_global", "Ctrl+Shift+B", "sc_pick_global",
                  "sc_group_tools", global_hotkey=True),
    # Pins whatever window the user is looking at, so it is only useful as an
    # OS-level hotkey — an in-app one would pin Videl itself.
    KeybindAction("always_on_top", "Ctrl+Shift+T", "sc_always_on_top",
                  "sc_group_tools", global_hotkey=True),
    # Grabs text off whatever is on screen, so like the picker it is only
    # useful when it works over other applications.
    KeybindAction("extract_text", "Ctrl+Shift+X", "sc_extract_text",
                  "sc_group_tools", global_hotkey=True),
    # Searches the machine, not Videl's tools (that is quick_search/Ctrl+K), so
    # it is only useful from anywhere.
    KeybindAction("find_files", "Ctrl+Shift+F", "sc_find_files",
                  "sc_group_tools", global_hotkey=True),
    KeybindAction("open_folder_rules", "Ctrl+Shift+R", "sc_folder_rules",
                  "sc_group_navigation"),
    # Presenter zoom. Global, because it zooms whatever is on screen. Not
    # Ctrl+Shift+Z: that is Redo in most editors, and a global hotkey claims
    # the combination system-wide, so it would break Redo everywhere.
    KeybindAction("zoom_screen", "Ctrl+Alt+Z", "sc_zoom_screen",
                  "sc_group_tools", global_hotkey=True),

    # Section jumps. Ctrl+1-9 by default; the trailing number is the section
    # index they navigate to, which is why they are generated rather than
    # hand-written (see _SECTION_JUMPS).
)

# (action id suffix, section id). By id, not index: Ctrl+9 was hardcoded to
# index 15 and labelled "History", but sections had since been inserted, so it
# opened Vocal Isolator. gui/app.py resolves the id when binding.
_SECTION_JUMPS: tuple[tuple[int, str], ...] = (
    (1, "download"),
    (2, "convert"),
    (3, "trim"),
    (4, "document"),
    (5, "gif"),
    (6, "compress"),
    (7, "merge"),
    (8, "spatial"),
    (9, "history"),
)

SECTION_JUMP_ACTIONS: tuple[KeybindAction, ...] = tuple(
    KeybindAction(f"section_{n}", f"Ctrl+{n}", f"sc_section_{n}", "sc_group_sections")
    for n, _section_id in _SECTION_JUMPS
)

ALL_ACTIONS: tuple[KeybindAction, ...] = ACTIONS + SECTION_JUMP_ACTIONS

SECTION_JUMP_TARGETS: dict[str, str] = {
    f"section_{n}": section_id for n, section_id in _SECTION_JUMPS
}

_BY_ID: dict[str, KeybindAction] = {a.id: a for a in ALL_ACTIONS}


def action(action_id: str) -> KeybindAction | None:
    return _BY_ID.get(action_id)


def is_valid(sequence: str) -> bool:
    """True when Qt can turn *sequence* into a usable single shortcut.

    Rejects the empty string, anything Qt cannot parse, and multi-step
    sequences like "Ctrl+K, Ctrl+B" — those are legal QKeySequences but cannot
    be registered as an OS hotkey and confuse the capture UI.
    """
    if not sequence or not sequence.strip():
        return False
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeySequence

    seq = QKeySequence(sequence)
    if seq.count() != 1 or seq.isEmpty():
        return False
    # Qt does NOT fail on nonsense: QKeySequence("NotAKey") parses to a
    # count-of-1 sequence whose key is Key_unknown and whose toString() is "".
    # Both have to be checked or a typo in config.json reads as a valid
    # binding.
    key = seq[0].key() if hasattr(seq[0], "key") else int(seq[0])
    if key == int(Qt.Key.Key_unknown):
        return False
    return bool(seq.toString(QKeySequence.SequenceFormat.PortableText))


def normalise(sequence: str) -> str:
    """Canonical spelling, so "ctrl+b" and "Ctrl+B" compare equal."""
    from PySide6.QtGui import QKeySequence

    return QKeySequence(sequence).toString(QKeySequence.SequenceFormat.PortableText)


def resolve(overrides: dict | None) -> dict[str, str]:
    """Final id -> sequence map: defaults with the user's valid overrides on top.

    An override that is empty, unparseable or a duplicate of an earlier binding
    is dropped rather than applied — a broken config must never leave an action
    unreachable.
    """
    resolved: dict[str, str] = {a.id: a.default for a in ALL_ACTIONS}
    if not overrides:
        return resolved

    taken = {}
    for act in ALL_ACTIONS:
        raw = overrides.get(act.id)
        if raw is None:
            continue
        if not isinstance(raw, str) or not is_valid(raw):
            continue
        resolved[act.id] = normalise(raw)

    # Drop any duplicate a hand-edited config may have introduced: first
    # declaration wins, the rest fall back to their default. An action is
    # NEVER left unbound — an unreachable action with no way to rebind it is
    # worse than two actions sharing a key, and the settings page surfaces the
    # remaining clash so the user can fix it.
    seen: dict[str, str] = {}
    for act in ALL_ACTIONS:
        seq = resolved[act.id]
        if seq in seen and seen[seq] != act.id:
            resolved[act.id] = act.default
        seen.setdefault(resolved[act.id], act.id)
    return resolved


def conflicts(resolved: dict[str, str]) -> dict[str, list[str]]:
    """sequence -> [action ids] for every sequence bound more than once."""
    by_sequence: dict[str, list[str]] = {}
    for action_id, seq in resolved.items():
        if seq:
            by_sequence.setdefault(seq, []).append(action_id)
    return {s: ids for s, ids in by_sequence.items() if len(ids) > 1}
