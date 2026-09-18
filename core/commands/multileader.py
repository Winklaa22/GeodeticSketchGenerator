from __future__ import annotations

from typing import List, Optional

from core.dxf_document import DXFDocument
from core.multileader import MultileaderSpec


class AddMultileaderCommand:
    def __init__(self, spec: MultileaderSpec) -> None:
        self._spec = spec.normalized()
        self.handles: List[str] = []
        self.handle: Optional[str] = None

    @property
    def spec(self) -> MultileaderSpec:
        return self._spec

    def execute(self, doc: DXFDocument) -> None:
        if self.handles:
            for handle in self.handles:
                doc.relink_entity(handle)
            return
        self.handles, self.handle = doc.add_multileader(self._spec)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self.handles:
            doc.unlink_entity(handle)
