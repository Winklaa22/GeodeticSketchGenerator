"""Editing commands — section 2 of the DXF edit command spec (Phase 1 subset:
delete only; move/copy/rotate/scale/vertex-edit/change-layer are later phases)."""
from __future__ import annotations

from typing import Iterable, List

from ezdxf.entities import DXFGraphic

from core.dxf_document import DXFDocument


class DeleteEntityCommand:
    """Deletes one or more entities. Reversible: entities are unlinked (kept
    alive in the entity database) rather than destroyed, so undo restores the
    exact same objects — see `DXFDocument.unlink_entity`/`restore_entity`."""

    def __init__(self, handles: Iterable[str]) -> None:
        self._handles: List[str] = list(handles)
        self._removed: List[DXFGraphic] = []

    def execute(self, doc: DXFDocument) -> None:
        self._removed = [doc.unlink_entity(handle) for handle in self._handles]

    def undo(self, doc: DXFDocument) -> None:
        for entity in self._removed:
            doc.restore_entity(entity)
        self._removed = []
