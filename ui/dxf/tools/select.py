from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.dxf_document import DXFDocument
from ui.dxf.tools.base import ToolSession, add_preview_item, parse_coordinate, preview_pen
from ui.i18n import tr

_MIN_AREA_SIZE = 1e-9


class SelectSimilarInAreaToolSession(ToolSession):

    def __init__(self, references: List[str]) -> None:
        super().__init__()
        self.prompt = tr("tool.select_area_first_corner")
        self._references = references
        self._first: Optional[Tuple[float, float]] = None
        self._second: Optional[Tuple[float, float]] = None
        self._preview_items: List[qw.QGraphicsItem] = []

    @property
    def crossing(self) -> bool:
        return self._first is not None and self._second is not None and self._second[0] < self._first[0]

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._first is None:
            self._first = point
            self.prompt = tr("tool.select_area_opposite_corner")
            return
        if abs(point[0] - self._first[0]) <= _MIN_AREA_SIZE or abs(point[1] - self._first[1]) <= _MIN_AREA_SIZE:
            return
        self._second = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=self._first)
        if coord is None:
            key = "common.point_xy_format" if self._first is None else "common.point_xy_or_rel_format"
            return tr(key, value=text)
        self.on_click(coord)
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)
        if self._first is None:
            return
        rect = qc.QRectF(qc.QPointF(*self._first), qc.QPointF(*point)).normalized()
        if rect.width() <= _MIN_AREA_SIZE or rect.height() <= _MIN_AREA_SIZE:
            return
        item = qw.QGraphicsRectItem(rect)
        pen = preview_pen()
        if point[0] >= self._first[0]:
            pen.setStyle(qc.Qt.PenStyle.SolidLine)
        item.setPen(pen)
        color = qg.QColor(pen.color())
        color.setAlpha(28)
        item.setBrush(qg.QBrush(color))
        add_preview_item(scene, item)
        self._preview_items.append(item)

    def _reset_preview(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def is_done(self) -> bool:
        return self._second is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        raise NotImplementedError

    def selection(self, doc: DXFDocument) -> Optional[List[str]]:
        assert self._first is not None and self._second is not None
        matched: List[str] = []
        seen = set()
        for reference in self._references:
            for handle in doc.find_similar_within(reference, (self._first, self._second), self.crossing):
                if handle not in seen:
                    seen.add(handle)
                    matched.append(handle)
        return matched

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)
