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
                      "Install it with: pip install 'file-organizer[gui-qt]' "
                      "or your distro package (e.g. python3-pyside6).",
                      file=sys.stderr)
                print(f"(import error: {exc})", file=sys.stderr)
                return 1
            print("note: PySide6 not found, falling back to legacy Tk interface. "
                  "Install PySide6 for the modern GUI.", file=sys.stderr)
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
