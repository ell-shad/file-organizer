"""Persistent user configuration (categories + preferences).

Stored as JSON in ``$XDG_CONFIG_HOME/file-organizer/settings.json``
(``~/.config/file-organizer/settings.json`` by default).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .core import DEFAULT_CATEGORIES, normalize_extensions, sanitize_folder_name

__all__ = ["load_settings", "save_settings", "default_config_path", "AppSettings"]

APP_DIR_NAME = "file-organizer"
SETTINGS_FILE = "settings.json"


def default_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(base) / APP_DIR_NAME / SETTINGS_FILE


class AppSettings:
    def __init__(
        self,
        categories: dict[str, list[str]] | None = None,
        include_other: bool = False,
        recursive: bool = False,
        conflict: str = "rename",
        delete_empty: bool = False,
        recent_dirs: list[str] | None = None,
    ) -> None:
        self.categories = categories if categories is not None else {
            k: list(v) for k, v in DEFAULT_CATEGORIES.items()
        }
        self.include_other = include_other
        self.recursive = recursive
        self.conflict = conflict if conflict in ("rename", "skip", "overwrite") else "rename"
        self.delete_empty = delete_empty
        self.recent_dirs = recent_dirs or []

    def to_dict(self) -> dict:
        return {
            "categories": self.categories,
            "include_other": self.include_other,
            "recursive": self.recursive,
            "conflict": self.conflict,
            "delete_empty": self.delete_empty,
            "recent_dirs": self.recent_dirs[:10],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        cats: dict[str, list[str]] = {}
        raw = data.get("categories", {})
        if isinstance(raw, dict):
            for name, exts in raw.items():
                try:
                    clean = sanitize_folder_name(str(name))
                    cats[clean] = normalize_extensions(exts or [])
                except ValueError:
                    continue  # drop unsafe entries from hand-edited configs
        if not cats:
            cats = {k: list(v) for k, v in DEFAULT_CATEGORIES.items()}
        obj = cls(categories=cats)
        obj.include_other = bool(data.get("include_other", False))
        obj.recursive = bool(data.get("recursive", False))
        if data.get("conflict") in ("rename", "skip", "overwrite"):
            obj.conflict = data["conflict"]
        obj.delete_empty = bool(data.get("delete_empty", False))
        recent = data.get("recent_dirs", [])
        if isinstance(recent, list):
            obj.recent_dirs = [str(d) for d in recent if isinstance(d, str)][:10]
        return obj

    def push_recent(self, directory: str) -> None:
        if directory in self.recent_dirs:
            self.recent_dirs.remove(directory)
        self.recent_dirs.insert(0, directory)
        self.recent_dirs = self.recent_dirs[:10]


def load_settings(path: str | os.PathLike | None = None) -> AppSettings:
    cfg = Path(path) if path else default_config_path()
    try:
        return AppSettings.from_dict(json.loads(cfg.read_text()))
    except (OSError, ValueError):
        return AppSettings()


def save_settings(settings: AppSettings, path: str | os.PathLike | None = None) -> str:
    cfg = Path(path) if path else default_config_path()
    cfg.parent.mkdir(parents=True, exist_ok=True)
    tmp = cfg.with_suffix(".tmp")
    tmp.write_text(json.dumps(settings.to_dict(), indent=2))
    tmp.replace(cfg)
    return str(cfg)
