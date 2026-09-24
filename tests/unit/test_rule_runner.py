"""RuleRunner: only watches what it should, and never runs uninvited."""
from __future__ import annotations

import os

import pytest

from core import folder_rules
from core.folder_rules import Rule

pytest.importorskip("PySide6.QtWidgets")

from PySide6.QtWidgets import QApplication        # noqa: E402
from core.rule_runner import RuleRunner            # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


class _Settings:
    """Minimal stand-in; RuleRunner only reads these two attributes."""

    def __init__(self, enabled=False, rules=None):
        self.folder_rules_enabled = enabled
        self.folder_rules = rules or []


def test_does_not_start_when_disabled(qapp, tmp_path):
    """The master switch is the whole safety story — it must actually gate."""
    watched = tmp_path / "w"
    watched.mkdir()
    rule = Rule(name="r", folder=str(watched), enabled=True,
                action="delete", patterns=["*.tmp"])
    runner = RuleRunner(_Settings(enabled=False, rules=[rule.to_dict()]))

    runner.start()

    assert not runner.running
    assert runner.watched_count() == 0


def test_watches_only_enabled_valid_rule_folders(qapp, tmp_path):
    good = tmp_path / "good"
    disabled = tmp_path / "disabled"
    dest = tmp_path / "dest"
    for d in (good, disabled, dest):
        d.mkdir()

    rules = [
        Rule(name="on", folder=str(good), enabled=True,
             action="move", destination=str(dest)).to_dict(),
        Rule(name="off", folder=str(disabled), enabled=False,
             action="move", destination=str(dest)).to_dict(),
        Rule(name="broken", folder=str(tmp_path / "missing"), enabled=True,
             action="move", destination=str(dest)).to_dict(),
    ]
    runner = RuleRunner(_Settings(enabled=True, rules=rules))
    runner.start()

    watched = [os.path.normcase(p) for p in runner._watcher.directories()]

    assert os.path.normcase(str(good)) in watched
    assert os.path.normcase(str(disabled)) not in watched
    assert len(watched) == 1, "a rule with a missing folder must not be watched"
    runner.stop()


def test_stop_releases_every_handle(qapp, tmp_path):
    """removePaths() leaves behind what it could not remove; stop() must loop."""
    dest = tmp_path / "dest"
    dest.mkdir()
    folders = []
    for i in range(5):
        f = tmp_path / f"w{i}"
        f.mkdir()
        folders.append(Rule(name=f"r{i}", folder=str(f), enabled=True,
                            action="move", destination=str(dest)).to_dict())

    runner = RuleRunner(_Settings(enabled=True, rules=folders))
    runner.start()
    assert runner.watched_count() == 5

    runner.stop()

    assert runner.watched_count() == 0
    assert not runner.running


def test_run_applies_rules(qapp, tmp_path, monkeypatch):
    watched = tmp_path / "w"
    dest = tmp_path / "d"
    watched.mkdir()
    dest.mkdir()
    (watched / "a.pdf").write_text("x")
    monkeypatch.setattr(folder_rules, "log_path", lambda: str(tmp_path / "log.jsonl"))

    rule = Rule(name="r", folder=str(watched), enabled=True, action="move",
                destination=str(dest), patterns=["*.pdf"])
    runner = RuleRunner(_Settings(enabled=True, rules=[rule.to_dict()]))

    runner._run()

    assert (dest / "a.pdf").exists()
    assert not (watched / "a.pdf").exists()
    runner.stop()


def test_run_is_a_no_op_once_the_switch_is_off(qapp, tmp_path, monkeypatch):
    """Even a queued timer must not act after the user turns rules off."""
    watched = tmp_path / "w"
    dest = tmp_path / "d"
    watched.mkdir()
    dest.mkdir()
    (watched / "a.pdf").write_text("x")
    monkeypatch.setattr(folder_rules, "log_path", lambda: str(tmp_path / "log.jsonl"))

    rule = Rule(name="r", folder=str(watched), enabled=True, action="move",
                destination=str(dest), patterns=["*.pdf"])
    settings = _Settings(enabled=True, rules=[rule.to_dict()])
    runner = RuleRunner(settings)
    settings.folder_rules_enabled = False

    runner._run()

    assert (watched / "a.pdf").exists(), "must not act while disabled"
