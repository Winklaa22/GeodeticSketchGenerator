from __future__ import annotations

import math
from typing import Optional

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from ui.i18n import tr
from ui.theme import Color as UiColor

DIAMETER = 68
_RING_MARGIN = 7
_TICK_LEN = 5
_LABEL_RADIUS_FRACTION = 0.68
_LETTERS = ((0.0, "N", True), (90.0, "E", False), (180.0, "S", False), (270.0, "W", False))


class RotationCompass(qw.QWidget):

    rotationChanged = qc.pyqtSignal(float)
    rotationCommitted = qc.pyqtSignal(float)
    resetRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(DIAMETER, DIAMETER)
        self.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr("compass.tooltip"))
        self._angle = 0.0
        self._drag_origin_angle: Optional[float] = None
        self._drag_start_value: Optional[float] = None

    def angle(self) -> float:
        return self._angle

    def set_angle(self, angle: float) -> None:
        angle = ((angle + 180.0) % 360.0) - 180.0
        if abs(angle - self._angle) > 1e-9:
            self._angle = angle
            self.update()

    def _center(self) -> qc.QPointF:
        return qc.QPointF(self.width() / 2.0, self.height() / 2.0)

    def _screen_angle(self, pos: qc.QPointF) -> float:
        center = self._center()
        return math.degrees(math.atan2(pos.y() - center.y(), pos.x() - center.x()))

    def mousePressEvent(self, event: qg.QMouseEvent) -> None:
        if event.button() != qc.Qt.MouseButton.LeftButton:
            return
        self._drag_origin_angle = self._screen_angle(event.position())
        self._drag_start_value = self._angle
        self.setCursor(qc.Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event: qg.QMouseEvent) -> None:
        if self._drag_origin_angle is None or self._drag_start_value is None:
            return
        current = self._screen_angle(event.position())
        delta = self._drag_origin_angle - current
        self.set_angle(self._drag_start_value + delta)
        self.rotationChanged.emit(self._angle)

    def mouseReleaseEvent(self, event: qg.QMouseEvent) -> None:
        if event.button() != qc.Qt.MouseButton.LeftButton or self._drag_origin_angle is None:
            return
        self._drag_origin_angle = None
        self._drag_start_value = None
        self.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        self.rotationCommitted.emit(self._angle)

    def mouseDoubleClickEvent(self, event: qg.QMouseEvent) -> None:
        if event.button() != qc.Qt.MouseButton.LeftButton:
            return
        self.resetRequested.emit()

    def paintEvent(self, event: qg.QPaintEvent) -> None:
        painter = qg.QPainter(self)
        painter.setRenderHint(qg.QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        radius = DIAMETER / 2.0 - _RING_MARGIN

        backing = qg.QColor(UiColor.SURFACE_RAISED)
        backing.setAlpha(230)
        painter.setPen(qc.Qt.PenStyle.NoPen)
        painter.setBrush(backing)
        painter.drawEllipse(qc.QPointF(cx, cy), DIAMETER / 2.0, DIAMETER / 2.0)

        painter.setPen(qg.QPen(qg.QColor(UiColor.BORDER_STRONG), 1.3))
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(qc.QPointF(cx, cy), radius, radius)

        tick_pen = qg.QPen(qg.QColor(UiColor.TEXT_FAINT), 1.0)
        painter.setPen(tick_pen)
        for step in range(12):
            deg = math.radians(step * 30.0 - self._angle - 90.0)
            inner = radius - _TICK_LEN
            painter.drawLine(
                qc.QPointF(cx + math.cos(deg) * inner, cy + math.sin(deg) * inner),
                qc.QPointF(cx + math.cos(deg) * radius, cy + math.sin(deg) * radius),
            )

        label_radius = radius * _LABEL_RADIUS_FRACTION
        font = painter.font()
        font.setPointSizeF(8.0)
        font.setBold(True)
        painter.setFont(font)
        for offset, letter, primary in _LETTERS:
            deg = math.radians(offset - self._angle - 90.0)
            x, y = cx + math.cos(deg) * label_radius, cy + math.sin(deg) * label_radius
            painter.setPen(qg.QColor(UiColor.ACCENT if primary else UiColor.TEXT_MUTED))
            painter.drawText(qc.QRectF(x - 8, y - 7, 16, 14), qc.Qt.AlignmentFlag.AlignCenter, letter)

        angle_font = painter.font()
        angle_font.setPointSizeF(7.0)
        angle_font.setBold(False)
        painter.setFont(angle_font)
        painter.setPen(qg.QColor(UiColor.TEXT_MUTED))
        shown = round(self._angle)
        painter.drawText(
            qc.QRectF(cx - 18, cy - 7, 36, 14), qc.Qt.AlignmentFlag.AlignCenter, tr("compass.degrees", value=shown)
        )
        painter.end()
