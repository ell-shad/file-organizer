"""Command-line interface: ``file-organizer <command>``.

The app is primarily a Debian-based Linux GUI app (.deb package), but the
CLI makes it scriptable and lets you run it straight from source::

    ./run.sh scan ~/Downloads
    ./run.sh organize ~/Downloads --dry-run

    file-organizer scan ~/Downloads
    file-organizer organize ~/Downloads --dry-run
    file-organizer organize ~/Downloads --only Images,Documents --conflict rename
    file-organizer undo
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .config import AppSettings, load_settings, save_settings
from .core import (
    OTHER_CATEGORY,
    clear_undo_log,
    delete_empty_dirs,
    find_empty_dirs,
    load_undo_log,
    organize_files,
    plan_moves,
    save_undo_log,
    scan_directory,
    undo_moves,
)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="file-organizer",
        description="Organize files by category (GUI app with scriptable CLI).",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="Show file distribution without moving anything.")
    s.add_argument("directory")
    s.add_argument("--json", action="store_true", help="Machine-readable output.")

    o = sub.add_parser("organize", help="Move files into category folders.")
    o.add_argument("directory")
    o.add_argument("--only", default="", help="Comma-separated categories (default: all).")
    o.add_argument("--include-other", action="store_true", help="Also file uncategorized items under 'Other/'.")
    o.add_argument("--recursive", action="store_true", help="Descend into subdirectories.")
    o.add_argument("--conflict", choices=["rename", "skip", "overwrite"], default="rename",
                   help="What to do when the destination exists (default: rename).")
    o.add_argument("--delete-empty", action="store_true", help="Remove empty folders afterwards.")
    o.add_argument("--dry-run", action="store_true", help="Print the plan, move nothing.")
    o.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")

    u = sub.add_parser("undo", help="Reverse the last organize run.")
    u.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")

    c = sub.add_parser("categories", help="List configured categories.")
    c.add_argument("--json", action="store_true")

    g = sub.add_parser("gui", help="Launch the graphical interface.")
    g.add_argument("--toolkit", choices=["auto", "qt", "tk"], default="auto")
    return p


def _require_dir(path: str) -> str:
    if not os.path.isdir(path):
        print(f"error: not a directory: {path}", file=sys.stderr)
        raise SystemExit(2)
    return os.path.abspath(path)


def cmd_scan(args, settings: AppSettings) -> int:
    directory = _require_dir(args.directory)
    result = scan_directory(directory, settings.categories)
    if args.json:
        print(json.dumps({"directory": directory, **result}, indent=2))
    else:
        print(f"{directory}: {result['total']} file(s)")
        for cat in sorted(result["counts"]):
            print(f"  {cat:15} {result['counts'][cat]}")
        for err in result["errors"]:
            print(f"  [error] {err}")
    return 0


def cmd_organize(args, settings: AppSettings) -> int:
    directory = _require_dir(args.directory)
    selected = None
    if args.only.strip():
        selected = [c.strip() for c in args.only.split(",") if c.strip()]
        unknown = [c for c in selected if c not in settings.categories and c != OTHER_CATEGORY]
        if unknown:
            print(f"error: unknown categories: {', '.join(unknown)}", file=sys.stderr)
            return 2
    plan = plan_moves(directory, settings.categories, selected,
                      include_other=args.include_other, recursive=args.recursive)
    if not plan:
        print("Nothing to organize.")
        return 0
    print(f"Plan: move {len(plan)} file(s) in {directory}")
    for item in plan[:20]:
        print(f"  {item['filename']}  ->  {item['category']}/")
    if len(plan) > 20:
        print(f"  … and {len(plan) - 20} more")
    if args.dry_run:
        return 0
    if not args.yes and sys.stdin.isatty():
        answer = input(f"Move {len(plan)} file(s)? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1

    total = len(plan)

    def progress(i: int, n: int, name: str) -> None:
        print(f"\r[{i}/{n}] {name}", end="", flush=True)

    result = organize_files(
        directory, settings.categories, selected,
        include_other=args.include_other, recursive=args.recursive,
        conflict=args.conflict, progress_cb=progress,
    )
    print()
    if result["moved"]:
        log_path = save_undo_log(result["moved"], directory)
        print(f"Moved {len(result['moved'])} file(s). Undo log: {log_path}")
    if result["skipped"]:
        print(f"Skipped {len(result['skipped'])} (destination exists).")
    for err in result["errors"]:
        print(f"[error] {err}")
    if args.delete_empty:
        cleanup = delete_empty_dirs(directory)
        print(f"Deleted {len(cleanup['deleted'])} empty folder(s).")
        for err in cleanup["errors"]:
            print(f"[error] {err}")
    if result["cancelled"]:
        return 130
    return 0 if not result["errors"] else 1


def cmd_undo(args, _settings: AppSettings) -> int:
    data = load_undo_log()
    if not data or not data.get("moved"):
        print("Nothing to undo (no undo log found).")
        return 0
    moves = data["moved"]
    print(f"Undo: move {len(moves)} file(s) back to {data.get('directory', '?')}")
    if not args.yes and sys.stdin.isatty():
        answer = input("Undo? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("Aborted.")
            return 1
    result = undo_moves(moves)
    print(f"Undid {result['undone']} file(s).")
    for err in result["errors"]:
        print(f"[error] {err}")
    clear_undo_log()
    return 0 if not result["errors"] else 1


def cmd_categories(args, settings: AppSettings) -> int:
    if args.json:
        print(json.dumps(settings.categories, indent=2))
    else:
        for cat, exts in settings.categories.items():
            print(f"{cat}: {', '.join(exts)}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.command == "scan":
        return cmd_scan(args, settings)
    if args.command == "organize":
        return cmd_organize(args, settings)
    if args.command == "undo":
        return cmd_undo(args, settings)
    if args.command == "categories":
        return cmd_categories(args, settings)
    if args.command == "gui":
        from .app import run_gui
        if isinstance(settings, AppSettings):
            save_settings(settings)  # ensure config dir exists, no-op otherwise
        return run_gui(toolkit=args.toolkit)
    parser.error(f"unknown command {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
