"""seen_version: empty on a first run (splash), set for configs from older versions (What's new)."""
import json

from core.settings import SettingsManager


def test_first_run_and_upgrade(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(SettingsManager, "get_config_path", classmethod(lambda cls: cfg))
    assert SettingsManager.load().seen_version == ""              # no config: first run

    cfg.write_text(json.dumps({"version": 13, "language": "ar"}), encoding="utf-8")
    s = SettingsManager.load()
    assert s.seen_version == "pre-5.3" and s.language == "ar"     # ran before: an update

    s.seen_version = "5.3.0"
    SettingsManager.save(s)
    assert SettingsManager.load().seen_version == "5.3.0"
