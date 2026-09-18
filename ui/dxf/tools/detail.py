from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtWidgets as qw

from core.commands.base import Command as EditCommand
from core.commands.detail_view import AddDetailViewCommand
from core.commands.multileader import AddMultileaderCommand
from core.detail_view import from_squares
from core.dxf_document import DXFDocument
from core.multileader import MultileaderSpec
from ui.dxf.tools.base import ToolSession, add_preview_item, parse_coordinate, preview_pen
from ui.dxf.tools.draw import add_leader_preview
from ui.i18n import tr

_MIN_BOX_SIZE = 1e-9


class DetailViewToolSession(ToolSession):

    def __init__(self) -> None:
        super().__init__()
        self.prompt = tr("tool.detail_source_center")
        self._source_center: Optional[Tuple[float, float]] = None
        self._source_size: Optional[float] = None
        self._frame_center: Optional[Tuple[float, float]] = None
        self._frame_size: Optional[float] = None
        self._preview_items: List[qw.QGraphicsItem] = []

    @staticmethod
    def _square_side(center: Tuple[float, float], point: Tuple[float, float]) -> float:
        return 2.0 * max(abs(point[0] - center[0]), abs(point[1] - center[1]))

    @staticmethod
    def _square_rect(center: Tuple[float, float], side: float) -> qc.QRectF:
        half = side / 2.0
        return qc.QRectF(center[0] - half, center[1] - half, side, side)

    def _pending_center(self) -> Optional[Tuple[float, float]]:
        if self._source_center is not None and self._source_size is None:
            return self._source_center
        if self._frame_center is not None and self._frame_size is None:
            return self._frame_center
        return None

    def on_click(self, point: Tuple[float, float]) -> None:
        if self._source_center is None:
            self._source_center = point
            self.prompt = tr("tool.detail_source_size")
            return
        if self._source_size is None:
            side = self._square_side(self._source_center, point)
            if side <= _MIN_BOX_SIZE:
                return
            self._source_size = side
            self.prompt = tr("tool.detail_frame_center")
            return
        if self._frame_center is None:
            self._frame_center = point
            self.prompt = tr("tool.detail_frame_size")
            return
        side = self._square_side(self._frame_center, point)
        if side <= _MIN_BOX_SIZE:
            return
        self._frame_size = side

    def on_text(self, text: str) -> Optional[str]:
        center = self._pending_center()
        if center is None:
            last = self._source_center
            coord = parse_coordinate(text, last_point=last)
            if coord is None:
                key = "common.point_xy_format" if last is None else "common.point_xy_or_rel_format"
                return tr(key, value=text)
            self.on_click(coord)
            return None
        try:
            side = float(text.strip())
        except ValueError:
            coord = parse_coordinate(text, last_point=center)
            if coord is None:
                return tr("tool.detail_size_or_point_numeric", value=text)
            side = self._square_side(center, coord)
        if side <= _MIN_BOX_SIZE:
            return tr("tool.detail_size_positive")
        if self._source_size is None:
            self._source_size = side
            self.prompt = tr("tool.detail_frame_center")
        else:
            self._frame_size = side
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)
        if self._source_center is None:
            return
        if self._source_size is None:
            self._add_preview_square(scene, self._source_center, self._square_side(self._source_center, point))
            return
        self._add_preview_square(scene, self._source_center, self._source_size)
        if self._frame_center is None:
            return
        self._add_preview_square(scene, self._frame_center, self._square_side(self._frame_center, point))

    def _add_preview_square(
        self, scene: qw.QGraphicsScene, center: Tuple[float, float], side: float
    ) -> None:
        if side <= _MIN_BOX_SIZE:
            return
        item = qw.QGraphicsRectItem(self._square_rect(center, side))
        item.setPen(preview_pen())
        add_preview_item(scene, item)
        self._preview_items.append(item)

    def _reset_preview(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def is_done(self) -> bool:
        return self._frame_size is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self.is_done()
        assert self._source_center is not None and self._source_size is not None
        assert self._frame_center is not None and self._frame_size is not None
        return AddDetailViewCommand(
            from_squares(
                self._source_center,
                self._source_size,
                self._frame_center,
                self._frame_size,
                doc.active_layer,
            )
        )

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)


_ARROW_HEIGHT = 0.6


class DetailArrowToolSession(ToolSession):
    """Pulls a leader arrow out of a fixed anchor - the detail frame's bottom edge."""

    def __init__(self, anchor: Tuple[float, float]) -> None:
        super().__init__()
        self.prompt = tr("tool.detail_arrow_target")
        self._anchor = anchor
        self._tip: Optional[Tuple[float, float]] = None
        self._preview_items: List[qw.QGraphicsItem] = []

    def _spec_for(self, tip: Tuple[float, float], layer: str = "0") -> MultileaderSpec:
        return MultileaderSpec(
            tip=tip,
            landing=None,
            text_position=self._anchor,
            text="",
            height=_ARROW_HEIGHT,
            attachment="right" if tip[0] >= self._anchor[0] else "left",
            landing_enabled=False,
            gap=0.0,
            layer=layer,
        ).normalized()

    def on_click(self, point: Tuple[float, float]) -> None:
        if point != self._anchor:
            self._tip = point

    def on_text(self, text: str) -> Optional[str]:
        coord = parse_coordinate(text, last_point=self._anchor)
        if coord is None:
            return tr("common.point_xy_or_rel_format", value=text)
        self.on_click(coord)
        return None

    def update_preview(self, point: Tuple[float, float], scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)
        if point == self._anchor:
            return
        add_leader_preview(scene, self._spec_for(point), self._preview_items)

    def _reset_preview(self, scene: qw.QGraphicsScene) -> None:
        for item in self._preview_items:
            scene.removeItem(item)
        self._preview_items = []

    def is_done(self) -> bool:
        return self._tip is not None

    def build_command(self, doc: DXFDocument) -> EditCommand:
        assert self._tip is not None
        return AddMultileaderCommand(self._spec_for(self._tip, doc.active_layer))

    def cleanup(self, scene: qw.QGraphicsScene) -> None:
        self._reset_preview(scene)
