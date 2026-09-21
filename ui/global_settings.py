from __future__ import annotations

import json
from typing import Optional

from PyQt6.QtCore import QSettings

from core.exceptions import ProjectFileError
from core.fonts import DEFAULT_FONT_ID, font_spec
from core.project import table_template_payload, template_from_payload
from core.table_template import TableTemplate, default_template

_DEFAULT_TABLE_ENABLED_KEY = "defaults/newProjectTableEnabled"
_DEFAULT_TABLE_JSON_KEY = "defaults/newProjectTableJson"
_DEFAULT_FONT_KEY = "defaults/newProjectFontId"
_DEFAULT_FONT_ITALIC_KEY = "defaults/newProjectFontItalic"
_DEFAULT_FONT_LINEWEIGHT_KEY = "defaults/newProjectFontLineweightMm"
_LANGUAGE_KEY = "general/language"
DEFAULT_LANGUAGE = "en"


def language(settings: QSettings) -> str:
    return str(settings.value(_LANGUAGE_KEY, DEFAULT_LANGUAGE))


def set_language(settings: QSettings, language_code: str) -> None:
    settings.setValue(_LANGUAGE_KEY, language_code)


def default_table_enabled(settings: QSettings) -> bool:
    return bool(settings.value(_DEFAULT_TABLE_ENABLED_KEY, True, type=bool))


def set_default_table_enabled(settings: QSettings, enabled: bool) -> None:
    settings.setValue(_DEFAULT_TABLE_ENABLED_KEY, enabled)


def has_custom_default_table(settings: QSettings) -> bool:
    return bool(settings.value(_DEFAULT_TABLE_JSON_KEY, ""))


def default_table_template(settings: QSettings) -> TableTemplate:
    raw = settings.value(_DEFAULT_TABLE_JSON_KEY, "")
    if not raw:
        return default_template()
    try:
        return template_from_payload(json.loads(raw))
    except (ValueError, ProjectFileError):
        return default_template()


def set_default_table_template(settings: QSettings, template: TableTemplate) -> None:
    settings.setValue(_DEFAULT_TABLE_JSON_KEY, json.dumps(table_template_payload(template)))


def new_project_table_template(settings: QSettings) -> TableTemplate:
    if not default_table_enabled(settings):
        return TableTemplate(columns=[], rows=[], cells=[])
    return default_table_template(settings)


def default_font_id(settings: QSettings) -> str:
    return font_spec(str(settings.value(_DEFAULT_FONT_KEY, DEFAULT_FONT_ID))).id


def set_default_font_id(settings: QSettings, font_id: str) -> None:
    settings.setValue(_DEFAULT_FONT_KEY, font_id)


def new_project_font_id(settings: QSettings) -> str:
    return default_font_id(settings)


def default_font_italic(settings: QSettings) -> bool:
    return bool(settings.value(_DEFAULT_FONT_ITALIC_KEY, False, type=bool))


def set_default_font_italic(settings: QSettings, italic: bool) -> None:
    settings.setValue(_DEFAULT_FONT_ITALIC_KEY, italic)


def new_project_font_italic(settings: QSettings) -> bool:
    return default_font_italic(settings)


def default_font_lineweight_mm(settings: QSettings) -> Optional[float]:
    raw = settings.value(_DEFAULT_FONT_LINEWEIGHT_KEY, "")
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def set_default_font_lineweight_mm(settings: QSettings, lineweight_mm: Optional[float]) -> None:
    settings.setValue(_DEFAULT_FONT_LINEWEIGHT_KEY, "" if lineweight_mm is None else str(lineweight_mm))


def new_project_font_lineweight_mm(settings: QSettings) -> Optional[float]:
    return default_font_lineweight_mm(settings)
