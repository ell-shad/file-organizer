# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [2.0.0] - 2026-10-09

Full rewrite of the app layer around a shared, tested core.

### Added
- New Qt (PySide6) interface: resizable, HiDPI-aware, threaded organize
  with progress + Cancel, preview table, pie chart without matplotlib,
  drag & drop, recent directories, dark-mode friendly
- CLI: `file-organizer scan|organize|undo|categories|gui` with `--dry-run`,
  `--only`, `--conflict`, `--include-other`, `--recursive`, `--delete-empty`
- Persistent settings (`~/.config/file-organizer/settings.json`) and
  cross-run undo log (`~/.local/state/file-organizer/last-run.json`)
- Tests: 35 pytest cases (core, config, CLI) + CI with .deb install check
- Packaging: updated `.deb`, portable tarball, source tarball, man page,
  self-contained PyInstaller binary (`build-standalone.sh`)
- GitHub automation: CI workflow, tag-triggered releases with artifacts,
  issue/PR templates, Dependabot
- Conflict policies: `rename` (default) / `skip` / `overwrite`
- Optional "Other" bucket and recursive mode

### Fixed (v2.0.1 audit)
- **`.deb` installed the legacy GUI on Ubuntu 24.04+/26.04**: the
  `Depends: python3-pyside6` metapackage does not exist on those releases
  (PySide6 ships as `python3-pyside6.qtcore`/`qtgui`/`qtwidgets`), so apt
  silently fell through to the Tk alternative. Now depends on the real
  subpackage names and installs the Qt interface by default
- **Empty chart in the Tk fallback**: without matplotlib the fallback drew
  nothing at all; it now renders a dependency-free pie + legend on a native
  Tk Canvas (covered by `tests/test_gui_tk_fallback.py`)
- **Silent fallback is no longer silent**: starting without Qt prints a clear
  banner naming the interface you actually got and how to install Qt

### Fixed (v1 audit)
- **Data loss**: organizing no longer silently overwrites same-named files
  at the destination (rename-by-default, `photo (1).jpg`)
- **Directory traversal**: category folder names are validated; `..`, `/`
  and absolute paths are rejected
- **Stats vs action mismatch**: uncategorized files were counted as "Other"
  but never organized; now an explicit opt-in
- **Fixed-size UI**: removed `800x800` + `resizable(False, False)`; layouts,
  splitters, and Qt scaling adapt to any resolution
- **Frozen UI**: moves run in a worker thread with cancellation
- **Crash on unreadable dirs**: `os.listdir` errors are reported, not raised
- **Risky cleanup**: hidden dirs, symlinks, and out-of-tree paths are never
  auto-deleted
- **Bad postinst**: no more `pip install --break-system-packages`; apt
  resolves `Depends` instead
- **Placeholder maintainer** in `DEBIAN/control` replaced with real contact
- **Hard matplotlib dependency** removed for the Qt UI (optional now)
- Desktop file modernized (TryExec, StartupNotify, standard categories)

## [1.0.0] - 2025-11-02

### Added
- Initial release
- File organization by category (Images, Videos, Documents, etc.)
- Visual statistics with pie charts
- Undo functionality
- Custom file type editor
- Empty folder deletion option
- GUI with progress tracking
- Desktop integration for Linux

### Known Issues
- None reported yet
