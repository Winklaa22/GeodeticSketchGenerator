from __future__ import annotations

from typing import Optional, Tuple

from PyQt6 import QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.blocks import InsertBlockCommand
from core.dxf_document import DXFDocument
from ui.dxf.tools.base import ToolSession, add_preview_item, parse_coordinate
from ui.i18n import tr
from ui.theme import Color as UiColor


class InsertBlockToolSession(ToolSession):
    """Places a block where the user clicks, the block itself following the cursor."""

    def __init__(
        self,
        name: str,
        outline: qg.QPainterPath,
        rotation: float = 0.0,
        scale: float = 1.0,
        source_path: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.prompt = tr("tool.specify_block_insertion_point", name=name)
        self._name = name
        self._outline = outline
        self._rotation = rotation
        self._scale = scale
        self._source_path = source_path
        self._insert: Optional[Tuple[float, float]] = None
        self._preview_item: Optional[qw.QGraphicsPathItem] = None

    def on_click(self, point: Tuple[float, float]) -> None:
        self._insert = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=None)
        if coord is None:
            return tr("common.point_xy_format", value=text)
        self._insert = coord
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        if self._insert is not None:
            return
        if self._preview_item is None:
            self._preview_item = qw.QGraphicsPathItem()
            pen = qg.QPen(qg.QColor(UiColor.ACCENT))
            pen.setCosmetic(True)
            self._preview_item.setPen(pen)
            add_preview_item(scene, self._preview_item)
        placement = qg.QTransform()
        placement.translate(point[0], point[1])
        placement.rotate(self._rotation)
        placement.scale(self._scale, self._scale)
        self._preview_item.setPath(placement.map(self._outline))

    def is_done(self) -> bool:
        return self._insert is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._insert is not None
        return InsertBlockCommand(
            self._name,
            self._insert,
            self._rotation,
            self._scale,
            doc.active_layer,
            self._source_path,
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        if self._preview_item is not None:
            scene.removeItem(self._preview_item)
            self._preview_item = None
