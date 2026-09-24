"""Marks on entities the generator drew, so a later run can replace its own work.

Kept in xdata rather than in memory because it has to outlive the undo history: a
project can be saved, reopened and generated again, and the run after that still has
to know which entities are its own to replace.
"""
from __future__ import annotations

from typing import Optional

GENERATED_APPID = "GSG_GENERATED"
_METADATA_VERSION = "1"


def mode_from_entity(entity) -> Optional[str]:
    """Which draw mode produced this entity, or None if the generator did not."""
    try:
        tags = entity.get_xdata(GENERATED_APPID)
    except (AttributeError, ValueError):
        return None
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) != 2 or values[0] != _METADATA_VERSION:
        return None
    return str(values[1])


def apply_metadata(entity, mode: str) -> None:
    entity.set_xdata(GENERATED_APPID, [(1000, _METADATA_VERSION), (1000, mode)])
