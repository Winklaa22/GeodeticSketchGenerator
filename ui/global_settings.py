from __future__ import annotations

import json

from PyQt6.QtCore import QSettings

from core.exceptions import ProjectFileError
from core.project import table_template_payload, template_from_payload
from core.table_template import TableTemplate, default_template

_DEFAULT_TABLE_ENABLED_KEY = "defaults/newProjectTableEnabled"
_DEFAULT_TABLE_JSON_KEY = "defaults/newProjectTableJson"


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
