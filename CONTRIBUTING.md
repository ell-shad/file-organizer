# Contributing to File Organizer

Thanks for helping out! A few ground rules keep the app safe (it moves
people's files, so care is warranted).

## Safety rules (required for any PR touching moves/deletes)

1. **Never silently overwrite.** The default conflict policy is `rename`.
   `overwrite` must always stay an explicit, confirmed opt-in.
2. **Folder names from users go through `sanitize_folder_name`.**
   No `..`, separators, or absolute paths — ever.
3. **Deletion stays conservative:** hidden dirs, symlinks, and anything
   outside the target directory are off-limits (`core.find_empty_dirs`).
4. **New logic needs tests:** `PYTHONPATH=src python -m pytest tests/ -q`
   must stay green. Add cases for new branches, especially collisions
   and invalid input.

## Workflow

1. Fork, create a branch (`git checkout -b fix/thing`).
2. For GUI work, test headless first:
   `QT_QPA_PLATFORM=offscreen python -c "…"` (see `.github/workflows/ci.yml`).
3. Update `CHANGELOG.md` (Unreleased section) and docs if behavior changes.
4. Open a PR using the template.

## Project layout

- `src/file_organizer/core.py` — GUI-independent logic (testable, no Qt/Tk imports)
- `src/file_organizer/gui_qt.py` — Qt interface (default)
- `src/file_organizer/gui_tk_legacy.py` — frozen v1 fallback (critical fixes only)
- `src/file_organizer/cli.py` — `file-organizer scan|organize|undo|categories|gui`
- `src/file_organizer/config.py` — XDG JSON settings
- `tests/` — pytest suite (must run without Qt installed)
