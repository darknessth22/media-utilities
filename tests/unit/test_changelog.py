"""assets/changelog.json feeds Settings, What's new and the card after an update."""
from core import changelog
from core.version import VERSION


def test_every_entry_is_complete_and_bilingual():
    entries = changelog.load()
    assert entries, "assets/changelog.json is missing or empty"
    versions = [e["version"] for e in entries]
    assert len(versions) == len(set(versions))
    for e in entries:
        assert e["en"] and len(e["en"]) == len(e["ar"]), e["version"]


def test_the_current_version_has_notes():
    # Add this release to the top of assets/changelog.json (WORKFLOW.md, Release).
    assert changelog.for_version(VERSION), f"no changelog entry for {VERSION}"
    # Newest first; during development the top entry may be the coming release.
    key = lambda v: tuple(int(x) for x in v.split("."))
    versions = [key(e["version"]) for e in changelog.load()]
    assert versions == sorted(versions, reverse=True) and versions[0] >= key(VERSION)
