from __future__ import annotations

import json
import os
from typing import List

from PyQt6.QtCore import QSettings

_SETTINGS_KEY = "recent_projects"
MAX_RECENTS = 20


def add_recent_project(settings: QSettings, path: str) -> None:
    recents = [p for p in _read(settings) if p != path and os.path.exists(p)]
    recents.insert(0, path)
    _write(settings, recents[:MAX_RECENTS])


def list_recent_projects(settings: QSettings) -> List[str]:
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
