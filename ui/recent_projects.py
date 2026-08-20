"""Recent-projects list — a small QSettings-backed MRU list shared between
the startup screen (ui/start_screen.py) and MainWindow's Save Project
action, so a newly saved project shows up in Recent next time the app
starts without either module needing to import the other."""
from __future__ import annotations

import json
import os
from typing import List

from PyQt6.QtCore import QSettings

_SETTINGS_KEY = "recent_projects"
MAX_RECENTS = 20


def add_recent_project(settings: QSettings, path: str) -> None:
    """Moves `path` to the front of the recent-projects list, dropping any
    entry whose file no longer exists and capping the list at MAX_RECENTS."""
    recents = [p for p in _read(settings) if p != path and os.path.exists(p)]
    recents.insert(0, path)
    _write(settings, recents[:MAX_RECENTS])


def list_recent_projects(settings: QSettings) -> List[str]:
    """Existing recent-project file paths, most-recently-used first. Any
    entry whose file has since been deleted/moved is dropped (and the
    stored list pruned to match)."""
    stored = _read(settings)
    existing = [p for p in stored if os.path.exists(p)]
    if existing != stored:
        _write(settings, existing)
    return existing


def remove_recent_project(settings: QSettings, path: str) -> None:
    _write(settings, [p for p in _read(settings) if p != path])


def _read(settings: QSettings) -> List[str]:
    raw = settings.value(_SETTINGS_KEY, "[]")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [str(p) for p in parsed] if isinstance(parsed, list) else []


def _write(settings: QSettings, paths: List[str]) -> None:
    settings.setValue(_SETTINGS_KEY, json.dumps(paths))
