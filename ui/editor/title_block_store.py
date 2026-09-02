from __future__ import annotations

import json
from dataclasses import asdict, fields

from PyQt6.QtCore import QSettings

from core.title_block import TitleBlockProfile

SETTINGS_KEY = "title_block_profile_v1"


def load_profile(settings: QSettings) -> TitleBlockProfile:
    raw = settings.value(SETTINGS_KEY, None)
    if raw:
        try:
            payload = json.loads(str(raw))
            names = {field.name for field in fields(TitleBlockProfile)}
            return TitleBlockProfile(
                **{key: str(value) for key, value in payload.items() if key in names}
            )
        except (ValueError, TypeError):
            pass
    return TitleBlockProfile()


def save_profile(settings: QSettings, profile: TitleBlockProfile) -> None:
    settings.setValue(SETTINGS_KEY, json.dumps(asdict(profile)))
