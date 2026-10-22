from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.dxf_document import DXFDocument


class SetEntityPropertyCommand:

    def __init__(self, handles: Iterable[str], key: str, value: Any) -> None:
        self._handles = list(handles)
        self._key = key
        self._value = value
        self._previous: List[Tuple[str, Tuple[Dict[str, object], Optional[str]]]] = []

    def execute(self, doc: DXFDocument) -> None:
        handles = doc.expand_annotation_handles(self._handles)
        self._previous = [(handle, doc.snapshot_entity_attribs(handle)) for handle in handles]
        try:
            for handle in handles:
                doc.set_entity_property(handle, self._key, self._value)
        except Exception:
            self.undo(doc)
            raise

    def undo(self, doc: DXFDocument) -> None:
        for handle, snapshot in reversed(self._previous):
            doc.restore_entity_attribs(handle, snapshot)
