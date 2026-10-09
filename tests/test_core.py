"""Core safety + logic tests. Run with ``pytest``."""

import os

import pytest

from file_organizer.core import (
    categorize_file,
    delete_empty_dirs,
    find_empty_dirs,
    normalize_extensions,
    organize_files,
    plan_moves,
    resolve_collision,
    sanitize_folder_name,
    scan_directory,
    undo_moves,
)

CATEGORIES = {
    "Images": [".jpg", ".png"],
    "Documents": [".pdf", ".txt"],
}


def make_tree(tmp_path, files):
    for name in files:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("data:" + name)
    return tmp_path


# --- validation ------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "  ", "..", ".", "../evil", "a/b", "a\\b",
                                 "/absolute", "C:\\x", "a\x00b", "x" * 101])
def test_sanitize_rejects_traversal(bad):
    with pytest.raises(ValueError):
        sanitize_folder_name(bad)


def test_sanitize_accepts_normal():
    assert sanitize_folder_name(" Disk Images ") == "Disk Images"
    assert sanitize_folder_name("My Docs 2024") == "My Docs 2024"


def test_normalize_extensions():
    assert normalize_extensions(["jpg", ".PNG", " .gif ", ""]) == [".gif", ".jpg", ".png"]
    with pytest.raises(ValueError):
        normalize_extensions(["a/b"])


def test_categorize_case_insensitive():
    assert categorize_file("PHOTO.JPG", CATEGORIES) == "Images"
    assert categorize_file("noext", CATEGORIES) is None


# --- scan / plan -----------------------------------------------------------

def test_scan_counts_other_and_skips_dirs(tmp_path):
    make_tree(tmp_path, ["a.jpg", "b.pdf", "mystery.zzz", "sub/nested.jpg"])
    (tmp_path / "sub").mkdir(exist_ok=True)
    result = scan_directory(tmp_path, CATEGORIES)
    assert result["total"] == 3  # top-level files only
    assert result["counts"]["Images"] == 1
    assert result["counts"]["Other"] == 1


def test_plan_respects_selection(tmp_path):
    make_tree(tmp_path, ["a.jpg", "b.pdf"])
    plan = plan_moves(tmp_path, CATEGORIES, selected=["Images"])
    assert [p["filename"] for p in plan] == ["a.jpg"]


def test_plan_other_opt_in(tmp_path):
    make_tree(tmp_path, ["mystery.zzz"])
    assert plan_moves(tmp_path, CATEGORIES) == []
    plan = plan_moves(tmp_path, CATEGORIES, include_other=True, selected=["Other"])
    assert len(plan) == 1 and plan[0]["category"] == "Other"


def test_plan_skips_symlinks(tmp_path):
    make_tree(tmp_path, ["real.jpg"])
    os.symlink(str(tmp_path / "real.jpg"), str(tmp_path / "link.jpg"))
    plan = plan_moves(tmp_path, CATEGORIES)
    assert [p["filename"] for p in plan] == ["real.jpg"]


def test_scan_missing_dir_reports_error_not_crash(tmp_path):
    result = scan_directory(tmp_path / "nope", CATEGORIES)
    assert result["total"] == 0 and result["errors"]


# --- organize: the data-loss guards ----------------------------------------

def test_organize_moves_and_undo_restores(tmp_path):
    make_tree(tmp_path, ["a.jpg", "b.pdf"])
    result = organize_files(tmp_path, CATEGORIES)
    assert len(result["moved"]) == 2 and not result["errors"]
    assert (tmp_path / "Images" / "a.jpg").exists()
    undo = undo_moves(result["moved"])
    assert undo["undone"] == 2
    assert (tmp_path / "a.jpg").exists()
    assert not (tmp_path / "Images" / "a.jpg").exists()


def test_organize_never_overwrites_by_default(tmp_path):
    make_tree(tmp_path, ["a.jpg", "Images/a.jpg"])
    (tmp_path / "Images" / "a.jpg").write_text("PRECIOUS")
    result = organize_files(tmp_path, CATEGORIES)  # default rename
    assert not result["errors"]
    assert (tmp_path / "Images" / "a.jpg").read_text() == "PRECIOUS"
    assert (tmp_path / "Images" / "a (1).jpg").exists()


def test_organize_skip_policy(tmp_path):
    make_tree(tmp_path, ["a.jpg", "Images/a.jpg"])
    result = organize_files(tmp_path, CATEGORIES, conflict="skip")
    assert len(result["moved"]) == 0
    assert len(result["skipped"]) == 1
    assert (tmp_path / "a.jpg").exists()  # left in place


def test_organize_invalid_conflict(tmp_path):
    with pytest.raises(ValueError):
        organize_files(tmp_path, CATEGORIES, conflict="nuke")


# --- empty folder cleanup ---------------------------------------------------

def test_find_empty_dirs_skips_hidden_and_symlinks(tmp_path):
    (tmp_path / "empty").mkdir()
    (tmp_path / ".hidden-empty").mkdir()
    (tmp_path / "full").mkdir()
    (tmp_path / "full" / "f.txt").write_text("x")
    os.symlink(str(tmp_path / "full"), str(tmp_path / "linkdir"))
    found = find_empty_dirs(tmp_path)
    assert [os.path.basename(p) for p in found] == ["empty"]


def test_delete_refuses_escape_and_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    result = delete_empty_dirs(tmp_path, dirs=[str(outside.parent / "nope"), str(outside)])
    # 'outside' is a direct child and empty -> deleted; bogus path reported
    assert len(result["deleted"]) == 1
    assert result["errors"]  # bogus path refused/reported


def test_resolve_collision_increments(tmp_path):
    target = tmp_path / "f.txt"
    target.write_text("x")
    first = resolve_collision(target)
    assert first.endswith("f (1).txt")
    assert resolve_collision(tmp_path / "fresh.txt").endswith("fresh.txt")
