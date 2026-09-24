"""Fast file search over two indexes.

1. **Windows Search** through ADO/OLE DB — free, always current, no scan of our
   own (11-30 ms per query). But it only covers what the user added to indexing
   options, which on a typical machine is C: and nothing else.
2. **Our own index** (``core/file_index.py``) for everything Windows ignores.
   Everything solves this by reading the NTFS MFT, which needs administrator
   rights; a background ``os.scandir`` pass does not.

Results from both are merged and de-duplicated by path, so the caller never
needs to care which index a hit came from.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass

_IS_WINDOWS = sys.platform == "win32"

_CONNECTION = "Provider=Search.CollatorDSO;Extended Properties='Application=Windows'"

# Folders that are technically indexed but never what someone is looking for.
_NOISE = (
    "\\appdata\\local\\temp\\",
    "\\windows\\winsxs\\",
    "\\$recycle.bin\\",
)


@dataclass(frozen=True)
class SearchHit:
    path: str
    name: str
    is_dir: bool
    size: int = 0

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


def _escape(term: str) -> str:
    """Make *term* safe inside a single-quoted SQL literal.

    The index dialect has no parameter binding, so the term is inlined — a
    stray apostrophe would otherwise break the query (or worse).
    """
    return term.replace("'", "''").replace("%", "").replace("[", "")


def index_available() -> bool:
    """True when EITHER index can answer a query.

    Our own index counts: a machine with Windows Search disabled is still fully
    searchable once a drive has been scanned, and reporting "unavailable" there
    would be wrong.
    """
    try:
        from core import file_index
        if file_index.indexed_drives():
            return True
    except Exception:
        pass
    return windows_index_available()


def windows_index_available() -> bool:
    """True when the Windows Search service answers a trivial query."""
    if not _IS_WINDOWS:
        return False
    try:
        import win32com.client as win32
    except Exception:
        return False
    try:
        conn = win32.Dispatch("ADODB.Connection")
        conn.Open(_CONNECTION)
        conn.Close()
        return True
    except Exception:
        return False


def search(term: str, limit: int = 40, folders_only: bool = False) -> list[SearchHit]:
    """Filenames containing *term*, from BOTH indexes, best matches first.

    Windows only indexes what the user added to indexing options — typically C:
    and nothing else — so a second drive is invisible to it. Results from our
    own index (core/file_index.py) are merged in, de-duplicated by path.
    """
    hits = _search_windows_index(term, limit, folders_only)

    try:
        from core import file_index
        seen = {h.path.lower() for h in hits}
        for path, name, isdir, size in file_index.search(term, limit=limit):
            if not path or path.lower() in seen:
                continue
            if folders_only and not isdir:
                continue
            seen.add(path.lower())
            hits.append(SearchHit(path=path, name=name,
                                  is_dir=bool(isdir), size=int(size or 0)))
    except Exception:
        pass

    hits.sort(key=lambda h: _rank(h, (term or "").strip().lower()))
    return hits[:limit]


def drive_order(hits: list[SearchHit]) -> list[str]:
    """Drive letters in the order results should be grouped.

    Ordered by where the best match sits, so the drive holding the exact hit
    leads — searching "lair" with the folder on E: puts every E: result first,
    then C:, then the rest.
    """
    best: dict[str, int] = {}
    for position, hit in enumerate(hits):
        letter = (hit.path[:1] or "?").upper()
        best.setdefault(letter, position)
    return sorted(best, key=lambda d: best[d])


def _rank(hit: SearchHit, term: str) -> tuple:
    """Sort key: best match first.

    Ordered by how the match relates to the WHOLE name, not merely whether the
    characters appear somewhere. Searching "lair" was returning
    ``flag_mc_bleuclair_SF.upk`` and ``skin_levain_flair_SF.upk`` above a folder
    literally named ``lair``, because every one of them "contains lair".
    """
    name = hit.name.lower()
    stem = os.path.splitext(name)[0]

    if name == term:
        tier = 0                    # the name IS the term, extension and all
    elif stem == term:
        tier = 1                    # "lair.lnk" — exact, but with a suffix
    elif stem.startswith(term) or name.startswith(term):
        tier = 2                    # prefix
    elif any(part == term for part in _split_words(stem)):
        tier = 3                    # whole word inside the name
    elif any(part.startswith(term) for part in _split_words(stem)):
        tier = 4                    # a word starts with it
    else:
        tier = 5                    # buried substring

    # Within a tier prefer folders (a user searching a bare word usually wants
    # the place, not one file inside it), then the shortest name.
    return (tier, not hit.is_dir, len(hit.name))


def _split_words(name: str) -> list[str]:
    """Break a filename into words on the usual separators."""
    out, current = [], []
    for ch in name:
        if ch.isalnum():
            current.append(ch)
        else:
            if current:
                out.append("".join(current))
                current = []
    if current:
        out.append("".join(current))
    return out


def _search_windows_index(term: str, limit: int = 40,
                          folders_only: bool = False) -> list[SearchHit]:
    """Filenames containing *term* from the Windows Search index.

    Substring rather than prefix matching: typing "report" should find
    "Q3 report.pdf", which a prefix query misses. Ordered by the index's own
    relevance rank, which puts shortcuts and recently used items first.
    """
    term = (term or "").strip()
    if not _IS_WINDOWS or len(term) < 2:
        return []
    try:
        import win32com.client as win32
    except Exception:
        return []

    safe = _escape(term)
    if not safe:
        return []

    where = [f"System.FileName LIKE '%{safe}%'"]
    if folders_only:
        where.append("System.ItemType = 'Directory'")

    sql = (
        "SELECT TOP {n} System.ItemPathDisplay, System.ItemNameDisplay, "
        "System.ItemType, System.Size "
        "FROM SYSTEMINDEX WHERE {w} "
        "ORDER BY System.Search.Rank DESC"
    ).format(n=max(1, min(int(limit) * 3, 200)), w=" AND ".join(where))

    conn = None
    try:
        conn = win32.Dispatch("ADODB.Connection")
        conn.Open(_CONNECTION)
        recordset = conn.Execute(sql)[0]
    except Exception:
        if conn is not None:
            try:
                conn.Close()
            except Exception:
                pass
        return []

    hits: list[SearchHit] = []
    try:
        while not recordset.EOF and len(hits) < limit:
            try:
                path = recordset.Fields.Item("System.ItemPathDisplay").Value or ""
                name = recordset.Fields.Item("System.ItemNameDisplay").Value or ""
                item_type = recordset.Fields.Item("System.ItemType").Value or ""
                size = recordset.Fields.Item("System.Size").Value or 0
            except Exception:
                recordset.MoveNext()
                continue
            recordset.MoveNext()

            if not path:
                continue
            lowered = path.lower()
            if any(noise in lowered for noise in _NOISE):
                continue
            hits.append(SearchHit(
                path=path,
                name=name or os.path.basename(path),
                is_dir=str(item_type).lower() in ("directory", ""),
                size=int(size or 0),
            ))
    finally:
        try:
            conn.Close()
        except Exception:
            pass
    return hits


def open_path(path: str) -> bool:
    """Open *path* with its default application."""
    if not path or not os.path.exists(path):
        return False
    try:
        os.startfile(path)          # noqa: S606 — Windows shell open, by design
        return True
    except Exception:
        return False


def reveal_in_explorer(path: str) -> bool:
    """Show *path* selected in Explorer."""
    if not path or not os.path.exists(path):
        return False
    import subprocess

    try:
        # /select, needs the path as ONE argument and no shell quoting games.
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        return True
    except Exception:
        return False
