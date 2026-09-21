from __future__ import annotations

from typing import Callable, Optional

import qtawesome as qta
from PyQt6.QtCore import QElapsedTimer, QEvent, QEventLoop, QObject, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Color, SPACE_LG
from ui.theme.icons import icon_manager

ProgressFn = Callable[[int], None]

FREQUENT_OP_DELAY_MS = 200
BLUR_RADIUS = 18.0
SCRIM_ALPHA = 170
SPINNER_SIZE = 64


def blurred_snapshot(widget: QWidget, radius: float = BLUR_RADIUS) -> QPixmap:
    source = widget.grab()
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(source)
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(radius)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    blurred = QPixmap(source.size())
    blurred.fill(Qt.GlobalColor.transparent)
    painter = QPainter(blurred)
    scene.render(painter, QRectF(blurred.rect()), QRectF(source.rect()))
    painter.end()
    return blurred


class LoadingOverlay(QWidget):

    def __init__(self, owner: QWidget) -> None:
        super().__init__(owner)
        self.setObjectName("loadingOverlay")
        self._owner = owner
        self._backdrop: Optional[QPixmap] = None
        self._delay_ms = 0
        self._elapsed = QElapsedTimer()
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_LG)
        layout.addStretch(1)

        self._spinner = qta.IconWidget()
        self._spinner.setIconSize(QSize(SPINNER_SIZE, SPINNER_SIZE))
        self._spinner.setFixedSize(QSize(SPINNER_SIZE, SPINNER_SIZE))
        self._spinner.setIcon(
            icon_manager.get(
                "loading", size=SPINNER_SIZE, color=Color.ACCENT, animation=qta.Spin(self._spinner)
            )
        )
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignHCenter)

        self._percent = QLabel("0%")
        self._percent.setObjectName("loadingPercent")
        self._percent.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._percent, 0, Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

    def begin(self, delay_ms: int = 0) -> None:
        self._backdrop = blurred_snapshot(self._owner)
        self.setGeometry(self._owner.rect())
        self._owner.installEventFilter(self)
        self._delay_ms = delay_ms
        self._elapsed.start()
        if delay_ms <= 0:
            self._reveal()
        self.report(0)

    def report(self, percent: int) -> None:
        self._percent.setText(f"{max(0, min(100, percent))}%")
        if not self.isVisible():
            if self._elapsed.elapsed() < self._delay_ms:
                return
            self._reveal()
        QApplication.processEvents(QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents)

    def _reveal(self) -> None:
        self.show()
        self.raise_()

    def finish(self) -> None:
        self._owner.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._owner and event.type() == QEvent.Type.Resize:
            self.setGeometry(self._owner.rect())
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._backdrop is not None:
            painter.drawPixmap(self.rect(), self._backdrop)
        scrim = QColor(Color.APP_BG)
        scrim.setAlpha(SCRIM_ALPHA)
        painter.fillRect(self.rect(), scrim)
        painter.end()
