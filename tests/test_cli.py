"""CLI tests (scan / organize --dry-run / organize / undo)."""

import json
import os

import pytest

from file_organizer import cli
from file_organizer.config import AppSettings


@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    d = tmp_path / "work"
    d.mkdir()
    (d / "a.jpg").write_text("img")
    (d / "b.pdf").write_text("doc")
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    return d


def test_scan_json(workdir, capsys):
    assert cli.main(["scan", str(workdir), "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["total"] == 2


def test_organize_dry_run_moves_nothing(workdir, capsys):
    assert cli.main(["organize", str(workdir), "--dry-run"]) == 0
    assert (workdir / "a.jpg").exists()  # untouched


def test_organize_and_undo_roundtrip(workdir, capsys):
    assert cli.main(["organize", str(workdir), "--yes"]) == 0
    assert (workdir / "Images" / "a.jpg").exists()
    capsys.readouterr()
    assert cli.main(["undo", "--yes"]) == 0
    assert (workdir / "a.jpg").exists()


def test_organize_unknown_category_rejected(workdir):
    assert cli.main(["organize", str(workdir), "--only", "Nope", "--yes"]) == 2


def test_scan_missing_dir_exits_2(tmp_path):
    with pytest.raises(SystemExit) as exc:
        cli.main(["scan", str(tmp_path / "nope")])
    assert exc.value.code == 2


def test_categories_list(workdir, capsys):
    settings = AppSettings()
    assert cli.cmd_categories(type("A", (), {"json": False})(), settings) == 0
    assert "Images" in capsys.readouterr().out
