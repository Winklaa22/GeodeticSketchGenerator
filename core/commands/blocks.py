from __future__ import annotations

from typing import Optional, Sequence

from core.blocks import read_block_file
from core.dxf_document import DXFDocument


class InsertBlockCommand:
    """Places one reference to a block, first defining it from its file if need be.

    Undo takes the reference away but leaves the definition, as AutoCAD does until a
    purge: other references may already use it, and a redo simply puts this one back.
    """

    def __init__(
        self,
        name: str,
        insert: Sequence[float],
        rotation: float = 0.0,
        scale: float = 1.0,
        layer: str = "0",
        source_path: Optional[str] = None,
    ) -> None:
        self._name = name
        self._insert = insert
        self._rotation = rotation
        self._scale = scale
        self._layer = layer
        self._source_path = source_path
        self._handle: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.relink_entity(self._handle)
            return
        if self._source_path is not None:
            doc.import_block(self._name, read_block_file(self._source_path))
        self._handle = doc.add_block_reference(
            self._name, self._insert, self._rotation, self._scale, self._layer
        )

    def undo(self, doc: DXFDocument) -> None:
        if self._handle is not None:
            doc.unlink_entity(self._handle)

    @property
    def handle(self) -> Optional[str]:
        return self._handle
