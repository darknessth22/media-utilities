"""File search over the Windows Search index."""
from __future__ import annotations

import os
import sys

import pytest

_WINDOWS = sys.platform == "win32"


def test_escape_neutralises_sql_metacharacters():
    """The index dialect has no parameter binding, so terms are inlined.

    An apostrophe would break the query; a bare % would match everything.
    """
    from core.file_search import _escape

    assert _escape("o'brien") == "o''brien"
    assert "%" not in _escape("100%")
    assert "[" not in _escape("file[1]")


@pytest.mark.parametrize("term", ["", "   ", "a"])
def test_short_terms_do_not_query(term):
    """One character would return thousands of rows and stall the UI."""
    from core.file_search import search

    assert search(term) == []


@pytest.mark.skipif(not _WINDOWS, reason="Windows Search is Windows-only")
def test_index_is_reachable():
    from core.file_search import index_available

    # Not an assert on True: a machine with indexing disabled is legitimate,
    # and the caller handles it. This just proves the probe does not raise.
    assert index_available() in (True, False)


@pytest.mark.skipif(not _WINDOWS, reason="Windows Search is Windows-only")
def test_search_returns_real_paths():
    from core.file_search import index_available, search

    if not index_available():
        pytest.skip("no Windows Search index on this machine")

    hits = search("windows", limit=5)
    assert isinstance(hits, list)
    for hit in hits:
        assert hit.path and hit.name
        assert hit.folder == os.path.dirname(hit.path)


@pytest.mark.skipif(not _WINDOWS, reason="Windows Search is Windows-only")
def test_noise_folders_are_filtered():
    from core.file_search import _NOISE, index_available, search

    if not index_available():
        pytest.skip("no Windows Search index on this machine")

    for hit in search("temp", limit=40):
        lowered = hit.path.lower()
        assert not any(noise in lowered for noise in _NOISE)


def test_open_path_rejects_a_missing_file(tmp_path):
    from core.file_search import open_path, reveal_in_explorer

    missing = str(tmp_path / "definitely-not-here.txt")
    assert open_path(missing) is False
    assert reveal_in_explorer(missing) is False
    assert open_path("") is False


@pytest.mark.parametrize("name,term,tier_name", [
    ("lair", "lair", "exact"),
    ("lair.txt", "lair", "exact stem"),
    ("lairs of the deep", "lair", "prefix"),
    ("my lair backup", "lair", "whole word"),
    ("skin_levain_flair_SF.upk", "lair", "buried"),
    ("flag_mc_bleuclair_SF.upk", "lair", "buried"),
])
def test_ranking_prefers_whole_name_matches(name, term, tier_name):
    """Searching "lair" was returning bleuclair/flair .upk files above a folder
    literally named "lair", because all of them "contain lair".
    """
    from core.file_search import SearchHit, _rank

    tier = _rank(SearchHit(path="x\\" + name, name=name, is_dir=False), term)[0]
    expected = {"exact": 0, "exact stem": 1, "prefix": 2,
                "whole word": 3, "buried": 5}[tier_name]
    assert tier == expected


def test_an_exact_folder_outranks_a_buried_file():
    from core.file_search import SearchHit, _rank

    folder = SearchHit(path="E:\clips\lair", name="lair", is_dir=True)
    buried = SearchHit(path="E:\g\skin_levain_flair_SF.upk",
                       name="skin_levain_flair_SF.upk", is_dir=False)
    assert _rank(folder, "lair") < _rank(buried, "lair")


def test_a_folder_wins_a_tie_against_a_file():
    """A bare word usually means "the place", not one file inside it."""
    from core.file_search import SearchHit, _rank

    folder = SearchHit(path="E:\clips", name="clips", is_dir=True)
    file_ = SearchHit(path="E:\clips.txt", name="clips", is_dir=False)
    assert _rank(folder, "clips") < _rank(file_, "clips")


def test_split_words_handles_the_usual_separators():
    from core.file_search import _split_words

    assert _split_words("skin_levain_flair_sf") == ["skin", "levain", "flair", "sf"]
    assert _split_words("my lair backup") == ["my", "lair", "backup"]
    assert _split_words("a-b.c") == ["a", "b", "c"]


def test_a_strictly_exact_name_beats_one_with_an_extension():
    """"lair" should rank above "lair.lnk" — the user typed the whole name."""
    from core.file_search import SearchHit, _rank

    exact = SearchHit(path=r"E:\clips\lair", name="lair", is_dir=True)
    with_ext = SearchHit(path=r"C:\Recent\lair.lnk", name="lair.lnk",
                         is_dir=False)
    assert _rank(exact, "lair") < _rank(with_ext, "lair")


def test_drive_order_follows_the_best_match():
    """The drive holding the best hit leads, so results group usefully."""
    from core.file_search import SearchHit, drive_order

    hits = [
        SearchHit(path=r"E:\clips\lair", name="lair", is_dir=True),
        SearchHit(path=r"C:\x\flair.upk", name="flair.upk", is_dir=False),
        SearchHit(path=r"E:\g\sinclair.upk", name="sinclair.upk", is_dir=False),
        SearchHit(path=r"D:\z\clair.txt", name="clair.txt", is_dir=False),
    ]
    assert drive_order(hits) == ["E", "C", "D"]


def test_drive_order_is_empty_for_no_hits():
    from core.file_search import drive_order

    assert drive_order([]) == []
