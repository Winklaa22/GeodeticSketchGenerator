from __future__ import annotations

import math
from typing import Optional

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw


HANDLE_ROLE = qc.Qt.ItemDataRole.UserRole


def x_scale(transform: qg.QTransform) -> float:
    return math.sqrt(transform.m11() * transform.m11() + transform.m21() * transform.m21())



class PointItem(qw.QAbstractGraphicsShapeItem):

    def __init__(self, x: float, y: float, brush: qg.QBrush) -> None:
        super().__init__()
        self._pos = qc.QPointF(x, y)
        self._radius = 1.2
        self.setPen(qg.QPen(qc.Qt.PenStyle.NoPen))
        self.setBrush(brush)

    def paint(
        self,
        painter: qg.QPainter,
        option: qw.QStyleOptionGraphicsItem,
        widget: Optional[qw.QWidget] = None,
    ) -> None:
        radius = self._radius / x_scale(painter.transform())
        painter.setBrush(self.brush())
        painter.setPen(qc.Qt.PenStyle.NoPen)
        painter.drawEllipse(self._pos, radius, radius)

    def boundingRect(self) -> qc.QRectF:
        r = 0.01
        return qc.QRectF(self._pos.x() - r, self._pos.y() - r, r * 2, r * 2)

