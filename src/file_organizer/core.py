"""File Organizer core logic (GUI-independent, testable).

v2.0: extracted from the legacy single-file Tk app so the Qt GUI,
the CLI, and the tests all share one safe implementation.

Safety fixes vs v1.x:
- never silently overwrite: default conflict policy is ``rename``
- folder names are sanitized (no ``..``, ``/``, absolute paths)
- symlinks are never followed for deletion and skipped when moving
- hidden directories (``.*``) are never auto-deleted
- permission errors are reported, not raised (no crash on listdir)
- ``Other`` (uncategorized) handling is explicit instead of
  count-but-ignore mismatch
"""

from __future__ import annotations

import json
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Callable, Iterable

__all__ = [
    "DEFAULT_CATEGORIES",
    "OTHER_CATEGORY",
    "sanitize_folder_name",
    "normalize_extensions",
    "categorize_file",
    "scan_directory",
    "plan_moves",
    "resolve_collision",
    "organize_files",
    "undo_moves",
    "find_empty_dirs",
    "delete_empty_dirs",
    "save_undo_log",
    "load_undo_log",
    "clear_undo_log",
    "default_undo_log_path",
]

OTHER_CATEGORY = "Other"

DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "Images": [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".tiff", ".heic", ".avif"],
    "Videos": [".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v"],
    "Archives": [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"],
    "Executables": [".exe", ".msi", ".appimage", ".deb", ".rpm", ".flatpakref"],
    "Documents": [".pdf", ".doc", ".docx", ".txt", ".xls", ".xlsx", ".ppt", ".pptx",
                  ".odt", ".ods", ".odp", ".csv", ".md", ".rtf", ".epub"],
    "Audio": [".mp3", ".wav", ".flac", ".aac", ".ogg", ".opus", ".m4a"],
    "Code": [".py", ".html", ".css", ".js", ".ts", ".c", ".cpp", ".h", ".java",
             ".go", ".rs", ".sh", ".json", ".xml", ".yml", ".yaml", ".toml"],
    "Fonts": [".ttf", ".otf", ".woff", ".woff2"],
    "Disk Images": [".iso", ".img", ".vdi", ".qcow2", ".vmdk"],
}


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def sanitize_folder_name(name: str) -> str:
    """Validate a user-supplied category/folder name.

    Returns the stripped name, raises :class:`ValueError` if it could
    escape the target directory (``..``, ``/``, absolute path, NUL…).
    """
    cleaned = name.strip().strip("/\\")
    if not cleaned:
        raise ValueError("folder name must not be empty")
    if "\x00" in cleaned:
        raise ValueError(f"invalid folder name {name!r}: NUL byte")
    if cleaned in {".", ".."}:
        raise ValueError(f"invalid folder name {name!r}")
    # Any path separator or parent reference anywhere is rejected.
    if "/" in cleaned or "\\" in cleaned:
        raise ValueError(f"folder name {name!r} must not contain path separators")
    if os.path.isabs(name.strip()):
        raise ValueError(f"folder name {name!r} must not be an absolute path")
    parts = cleaned.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"folder name {name!r} must not contain '..'")
    if len(cleaned) > 100:
        raise ValueError(f"folder name {name!r} is too long (max 100 chars)")
    return cleaned


def normalize_extensions(raw: Iterable[str]) -> list[str]:
    """Normalize ``['jpg', '.PNG', '']`` -> ``['.jpg', '.png']`` (sorted, unique)."""
    out: set[str] = set()
    for ext in raw:
        ext = ext.strip().lower()
        if not ext:
            continue
        if not ext.startswith("."):
            ext = f".{ext}"
        if len(ext) < 2 or len(ext) > 12 or "/" in ext or "\\" in ext or "\x00" in ext:
            raise ValueError(f"invalid extension {ext!r}")
        out.add(ext)
    return sorted(out)


def categorize_file(filename: str, categories: dict[str, list[str]]) -> str | None:
    """Return the category for *filename* or ``None`` if uncategorized."""
    ext = os.path.splitext(filename)[1].lower()
    for category, extensions in categories.items():
        if ext in extensions:
            return category
    return None


# ---------------------------------------------------------------------------
# Scanning / planning (no filesystem mutation)
# ---------------------------------------------------------------------------

def _iter_top_level_files(directory: Path):
    """Yield (DirEntry) for regular files, collecting errors instead of crashing."""
    try:
        with os.scandir(directory) as it:
            entries = list(it)
    except OSError as exc:
        raise OSError(f"cannot list directory {directory}: {exc.strerror or exc}") from exc
    return entries


def scan_directory(
    directory: str | os.PathLike,
    categories: dict[str, list[str]],
) -> dict:
    """Scan top-level files. Returns ``{'counts', 'total', 'files', 'errors'}``.

    Never raises on unreadable entries — problems go into ``errors``.
    Symlinks are listed but flagged (``is_symlink``) so callers can skip them.
    """
    base = Path(directory)
    counts: dict[str, int] = defaultdict(int)
    files: list[dict] = []
    errors: list[str] = []
    try:
        entries = _iter_top_level_files(base)
    except OSError as exc:
        return {"counts": {}, "total": 0, "files": [], "errors": [str(exc)]}

    for entry in entries:
        try:
            if entry.is_symlink():
                # Count symlinks separately; organizer skips them by default.
                if entry.is_file(follow_symlinks=False):
                    counts["Symlinks (skipped)"] += 1
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
        except OSError as exc:
            errors.append(f"{entry.name}: {exc}")
            continue
        stat = None
        try:
            stat = entry.stat(follow_symlinks=False)
        except OSError:
            pass
        category = categorize_file(entry.name, categories)
        counts[category if category else OTHER_CATEGORY] += 1
        files.append({
            "name": entry.name,
            "path": str(Path(entry.path)),
            "size": stat.st_size if stat else -1,
            "category": category,
        })
    return {"counts": dict(counts), "total": len(files), "files": files, "errors": errors}


def plan_moves(
    directory: str | os.PathLike,
    categories: dict[str, list[str]],
    selected: Iterable[str] | None = None,
    include_other: bool = False,
    recursive: bool = False,
) -> list[dict]:
    """Compute the move plan without touching the filesystem.

    Each item: ``{'src', 'dest_dir', 'dest_path', 'filename', 'category'}``.
    Raises :class:`ValueError` on unsafe folder names.
    """
    base = Path(directory)
    wanted = set(selected) if selected is not None else set(categories)
    plan: list[dict] = []

    def consider(path: Path) -> None:
        category = categorize_file(path.name, categories)
        if category is None:
            if not include_other or OTHER_CATEGORY not in wanted:
                return
            category = OTHER_CATEGORY
        elif category not in wanted:
            return
        folder = sanitize_folder_name(category)
        dest_dir = base / folder
        plan.append({
            "src": str(path),
            "dest_dir": str(dest_dir),
            "dest_path": str(dest_dir / path.name),
            "filename": path.name,
            "category": category,
        })

    if recursive:
        try:
            for root, dirs, filenames in os.walk(base, followlinks=False):
                # Never descend into our own destination folders or hidden dirs.
                dirs[:] = [d for d in dirs
                           if d not in set(categories) | {OTHER_CATEGORY}
                           and not d.startswith(".")
                           and not os.path.islink(os.path.join(root, d))]
                for name in filenames:
                    full = os.path.join(root, name)
                    if os.path.islink(full):
                        continue
                    consider(Path(full))
        except OSError:
            pass
    else:
        try:
            entries = _iter_top_level_files(base)
        except OSError:
            return []
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
            except OSError:
                continue
            consider(Path(entry.path))
    return plan


# ---------------------------------------------------------------------------
# Mutation: organize / undo / cleanup
# ---------------------------------------------------------------------------

def resolve_collision(dest: str | os.PathLike) -> str:
    """Return a non-existing path by appending ``' (1)'``, ``' (2)'`` …."""
    dest_path = Path(dest)
    if not dest_path.exists() and not dest_path.is_symlink():
        return str(dest_path)
    stem, suffix = dest_path.stem, dest_path.suffix
    parent = dest_path.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            return str(candidate)
        i += 1


def organize_files(
    directory: str | os.PathLike,
    categories: dict[str, list[str]],
    selected: Iterable[str] | None = None,
    include_other: bool = False,
    recursive: bool = False,
    conflict: str = "rename",
    progress_cb: Callable[[int, int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict:
    """Move files into category folders.

    ``conflict``: ``'rename'`` (default, never overwrites), ``'skip'``,
    or ``'overwrite'`` (explicit opt-in only).

    Returns ``{'moved', 'skipped', 'errors', 'cancelled'}`` where
    ``moved`` items are ``{'src', 'dest'}`` (current → original) for undo.
    """
    if conflict not in ("rename", "skip", "overwrite"):
        raise ValueError(f"unknown conflict policy: {conflict!r}")
    plan = plan_moves(directory, categories, selected, include_other, recursive)
    moved: list[dict] = []
    skipped: list[dict] = []
    errors: list[str] = []
    total = len(plan)

    for i, item in enumerate(plan):
        if cancel_check is not None and cancel_check():
            return {"moved": moved, "skipped": skipped, "errors": errors,
                    "cancelled": True, "total": total}
        src, dest_dir = item["src"], item["dest_dir"]
        dest_path = item["dest_path"]
        try:
            os.makedirs(dest_dir, exist_ok=True)
        except OSError as exc:
            errors.append(f"{item['filename']}: cannot create {dest_dir}: {exc}")
            continue
        final_dest = dest_path
        if os.path.exists(dest_path) or os.path.islink(dest_path):
            if conflict == "skip":
                skipped.append({**item, "reason": "destination exists"})
                if progress_cb:
                    progress_cb(i + 1, total, item["filename"])
                continue
            if conflict == "rename":
                final_dest = resolve_collision(dest_path)
            # 'overwrite' keeps dest_path
        try:
            shutil.move(src, final_dest)
            moved.append({"src": final_dest, "dest": src})
        except OSError as exc:
            errors.append(f"{item['filename']}: {exc}")
        if progress_cb:
            progress_cb(i + 1, total, item["filename"])

    return {"moved": moved, "skipped": skipped, "errors": errors,
            "cancelled": False, "total": total}


def undo_moves(move_log: list[dict]) -> dict:
    """Reverse a move log from :func:`organize_files` (newest first)."""
    undone = 0
    errors: list[str] = []
    for move in reversed(move_log):
        current, original = move["src"], move["dest"]
        try:
            if not os.path.exists(current) and not os.path.islink(current):
                errors.append(f"{os.path.basename(current)}: already gone, skipped")
                continue
            parent = os.path.dirname(original)
            if parent:
                os.makedirs(parent, exist_ok=True)
            target = original
            if os.path.exists(target) or os.path.islink(target):
                target = resolve_collision(target)
            shutil.move(current, target)
            undone += 1
        except OSError as exc:
            errors.append(f"{os.path.basename(current)}: {exc}")
    return {"undone": undone, "errors": errors}


def find_empty_dirs(
    directory: str | os.PathLike,
    skip_hidden: bool = True,
    skip_names: Iterable[str] | None = ("Other",),
) -> list[str]:
    """List empty top-level directories safe to remove.

    Never returns symlinks, hidden dirs (when *skip_hidden*), or
    non-directories. Callers should still confirm with the user.
    """
    base = Path(directory)
    found: list[str] = []
    try:
        entries = _iter_top_level_files(base)
    except OSError:
        return []
    skip = set(skip_names or ())
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
        except OSError:
            continue
        if skip_hidden and entry.name.startswith("."):
            continue
        if entry.name in skip:
            continue
        try:
            if not os.listdir(entry.path):
                found.append(entry.path)
        except OSError:
            continue
    return found


def delete_empty_dirs(
    directory: str | os.PathLike,
    dirs: Iterable[str | os.PathLike] | None = None,
) -> dict:
    """Delete *dirs* (default: :func:`find_empty_dirs`). Re-validates each."""
    base = os.path.realpath(directory)
    targets = list(dirs) if dirs is not None else find_empty_dirs(directory)
    deleted: list[str] = []
    errors: list[str] = []
    for target in targets:
        real = os.path.realpath(target)
        # Containment check: only delete direct children of base.
        if os.path.dirname(real) != base:
            errors.append(f"{target}: outside target directory, refused")
            continue
        if os.path.islink(target):
            errors.append(f"{target}: is a symlink, refused")
            continue
        if not os.path.exists(target):
            errors.append(f"{target}: does not exist")
            continue
        try:
            if not os.path.isdir(target) or os.listdir(target):
                continue
            os.rmdir(target)
            deleted.append(target)
        except OSError as exc:
            errors.append(f"{target}: {exc}")
    return {"deleted": deleted, "errors": errors}


# ---------------------------------------------------------------------------
# Persistent undo log (XDG state dir so CLI undo works across runs)
# ---------------------------------------------------------------------------

def default_undo_log_path() -> Path:
    state = os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state"))
    return Path(state) / "file-organizer" / "last-run.json"


def save_undo_log(moved: list[dict], directory: str, path: str | os.PathLike | None = None) -> str:
    log_path = Path(path) if path else default_undo_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps({"directory": directory, "moved": moved}, indent=2))
    return str(log_path)


def load_undo_log(path: str | os.PathLike | None = None) -> dict | None:
    log_path = Path(path) if path else default_undo_log_path()
    try:
        data = json.loads(log_path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("moved"), list):
        return None
    return data


def clear_undo_log(path: str | os.PathLike | None = None) -> None:
    try:
        (Path(path) if path else default_undo_log_path()).unlink(missing_ok=True)
    except OSError:
        pass
