"""GUI launcher: Qt preferred, legacy Tk fallback.

``file-organizer gui --toolkit auto`` (default) tries PySide6 first and
falls back to the legacy Tk interface with a console notice.
"""

from __future__ import annotations

import sys


def run_gui(toolkit: str = "auto") -> int:
    if toolkit not in ("auto", "qt", "tk"):
        print(f"error: unknown toolkit {toolkit!r} (choose auto, qt, tk)", file=sys.stderr)
        return 2
    if toolkit in ("auto", "qt"):
        try:
            from . import gui_qt
            return gui_qt.run()
        except ImportError as exc:
            if toolkit == "qt":
                print("error: PySide6 is required for the Qt interface.\n"
                      "  Debian/Ubuntu: sudo apt install python3-pyside6.qtcore "
                      "python3-pyside6.qtgui python3-pyside6.qtwidgets\n"
                      "  or pip install PySide6",
                      file=sys.stderr)
                print(f"(import error: {exc})", file=sys.stderr)
                return 1
            # Auto mode must not silently look like the old app: the legacy
            # fallback looks different and lacks preview/threading, so tell the
            # user exactly which interface they got and how to get the Qt one.
            print("=" * 68, file=sys.stderr)
            print("WARNING: PySide6 not found — starting the LEGACY Tk interface.", file=sys.stderr)
            print("  This is the old v1 UI. It has no preview, no progress bar", file=sys.stderr)
            print("  and no HiDPI scaling.", file=sys.stderr)
            print("  For the modern Qt interface:", file=sys.stderr)
            print("    sudo apt install python3-pyside6.qtcore python3-pyside6.qtgui \\", file=sys.stderr)
            print("                         python3-pyside6.qtwidgets", file=sys.stderr)
            print("  (or use the self-contained binary from the Releases page)", file=sys.stderr)
            print("=" * 68, file=sys.stderr)
    # Tk fallback (legacy v1 interface, no matplotlib required)
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("error: neither PySide6 nor Tkinter is available. "
              "Install python3-pyside6 or python3-tk.", file=sys.stderr)
        return 1
    from . import gui_tk_legacy as legacy
    import tkinter as tk
    root = tk.Tk()
    try:
        root.wm_class("file-organizer")
    except Exception:
        pass
    legacy.FileOrganizerApp(root)
    root.mainloop()
    return 0
