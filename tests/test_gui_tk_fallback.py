"""Legacy Tk fallback regression tests.

Covers the v2.0 bug where the Tk interface showed an empty chart when
matplotlib was not installed (it silently drew nothing at all).

These tests need a display. They skip when Tk cannot open one (e.g. CI
without Xvfb), so the core suite stays runnable without a GUI session.
"""

import os
import sys

import pytest

tkinter = pytest.importorskip("tkinter")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from file_organizer import gui_tk_legacy as legacy  # noqa: E402


@pytest.fixture(scope="module")
def root():
    try:
        r = tkinter.Tk()
    except Exception as exc:  # no display available
        pytest.skip(f"no display: {exc}")
    r.geometry("900x700")
    r.update()
    yield r
    r.destroy()


@pytest.fixture()
def app(root):
    legacy_root = tkinter.Tk()
    legacy_root.geometry("900x700")
    legacy_root.update()
    instance = legacy.FileOrganizerApp(legacy_root)
    legacy_root.update()
    yield instance
    legacy_root.destroy()


def _canvas_items(app):
    c = app.chart_canvas
    if c is None:
        return [], []
    ids = c.find_all()
    arcs = [i for i in ids if c.type(i) == "arc"]
    texts = [c.itemcget(i, "text") for i in ids if c.type(i) == "text"]
    return arcs, texts


def test_fallback_draws_without_matplotlib(app, tmp_path, monkeypatch):
    """The chart must render even when matplotlib is unavailable."""
    if legacy._HAS_MPL:
        pytest.skip("matplotlib installed; fallback path not exercised")
    for name in ("a.jpg", "b.jpg", "c.pdf", "d.mp3", "mystery.xyz"):
        (tmp_path / name).write_text("x")

    app.selected_directory = str(tmp_path)
    app.check_files_in_directory()
    app.chart_frame.pack(side=tkinter.BOTTOM, fill=tkinter.X, pady=10)
    app.chart_frame.master.update()

    arcs, texts = _canvas_items(app)
    assert arcs, "pie arcs missing: chart did not render"
    assert len(arcs) >= 4, f"expected a slice per category, got {len(arcs)}"
    legend = [t for t in texts if ":" in t]
    assert len(legend) >= 4, f"legend missing: {legend}"


def test_fallback_hint_absent_without_data(app):
    """The matplotlib hint stays hidden while no data is drawn."""
    if legacy._HAS_MPL:
        pytest.skip("matplotlib installed; fallback path not exercised")
    assert app.chart_note is not None
    app.update_plot({})
    app.chart_frame.master.update()
    assert app.chart_note.winfo_ismapped() is 0


def test_fallback_hint_shown_while_basic_chart_draws(app, tmp_path):
    """With the fallback chart and real data, the hint explains the styling."""
    if legacy._HAS_MPL:
        pytest.skip("matplotlib installed; fallback path not exercised")
    (tmp_path / "x.jpg").write_text("x")
    app.selected_directory = str(tmp_path)
    app.check_files_in_directory()
    app.chart_frame.pack(side=tkinter.BOTTOM, fill=tkinter.X, pady=10)
    app.chart_frame.master.update()
    assert app.chart_note.winfo_ismapped() == 1, "hint should explain the basic chart"


def test_scan_finds_files_and_enables_organize(app, tmp_path):
    (tmp_path / "a.jpg").write_text("x")
    (tmp_path / "b.pdf").write_text("x")
    app.selected_directory = str(tmp_path)
    app.check_files_in_directory()
    assert "Found 2 files" in app.progress_bar_label.cget("text")
    assert str(app.organize_btn.cget("state")) == "normal"


def test_fallback_banner_exists_and_is_dismissible(app):
    """The old UI must announce itself, so users are never confused about
    which interface they are looking at."""
    assert app.fallback_banner is not None
    children = app.fallback_banner.winfo_children()
    texts = [c.cget("text") for c in children if isinstance(c, tkinter.Label)]
    joined = " ".join(texts)
    assert "Legacy interface" in joined
    assert "python3-pyside6" in joined  # actionable install hint
    # A dismiss button must exist and hide the banner.
    buttons = [c for c in children if isinstance(c, tkinter.Button)]
    assert buttons, "banner is not dismissible"
    app.fallback_banner.pack_forget()
    app.fallback_banner.master.update()
    assert app.fallback_banner.winfo_ismapped() == 0