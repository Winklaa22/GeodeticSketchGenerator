from __future__ import annotations

from typing import Dict, Optional

from PyQt6 import QtCore as qc, QtWidgets as qw

from ui.i18n import tr
from ui.theme import Color as UiColor, ICON_MD, SPACE_XS
from ui.theme.icons import icon_manager


class DxfToolbar(qw.QWidget):

    pointRequested = qc.pyqtSignal()
    textRequested = qc.pyqtSignal()
    lineRequested = qc.pyqtSignal()
    circleRequested = qc.pyqtSignal()
    pipeRequested = qc.pyqtSignal()
    multileaderRequested = qc.pyqtSignal()
    selectRequested = qc.pyqtSignal()
    moveRequested = qc.pyqtSignal()
    rotateRequested = qc.pyqtSignal()
    scaleRequested = qc.pyqtSignal()
    rotateEachRequested = qc.pyqtSignal()
    scaleEachRequested = qc.pyqtSignal()
    selectSimilarRequested = qc.pyqtSignal()
    eraseRequested = qc.pyqtSignal()
    zoomExtentsRequested = qc.pyqtSignal()
    zoomInRequested = qc.pyqtSignal()
    zoomOutRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dxfToolbar")
        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        self._tool_buttons: Dict[str, qw.QToolButton] = {}
        self._tool_signals = {
            "point": self.pointRequested,
            "text": self.textRequested,
            "line": self.lineRequested,
            "circle": self.circleRequested,
            "pipe": self.pipeRequested,
            "multileader": self.multileaderRequested,
            "move": self.moveRequested,
            "rotate": self.rotateRequested,
            "scale": self.scaleRequested,
            "rotate_each": self.rotateEachRequested,
            "scale_each": self.scaleEachRequested,
        }
        self._tool_icon_names = {
            "select": "select_tool",
            "point": "point_tool",
            "text": "text_tool",
            "line": "line_tool",
            "circle": "circle_tool",
            "pipe": "pipe_tool",
            "multileader": "multileader_tool",
            "move": "move_tool",
            "rotate": "rotate_tool",
            "scale": "scale_tool",
            "rotate_each": "rotate_each_tool",
            "scale_each": "scale_each_tool",
        }

        self._add_tool_button(layout, "select", "select_tool", tr("toolbar.select_tooltip"))
        self._select_similar_btn = self._add_plain_button(
            layout, "select_similar_tool", tr("toolbar.select_similar_tooltip"), self.selectSimilarRequested
        )
        layout.addWidget(self._separator())
        self._add_tool_button(layout, "point", "point_tool", tr("toolbar.point_tooltip"))
        self._add_tool_button(layout, "text", "text_tool", tr("toolbar.text_tooltip"))
        self._add_tool_button(layout, "line", "line_tool", tr("toolbar.line_tooltip"))
        self._add_tool_button(layout, "circle", "circle_tool", tr("toolbar.circle_tooltip"))
        self._add_tool_button(layout, "pipe", "pipe_tool", tr("toolbar.pipe_tooltip"))
        self._add_tool_button(layout, "multileader", "multileader_tool", tr("toolbar.multileader_tooltip"))
        layout.addWidget(self._separator())
        self._add_tool_button(layout, "move", "move_tool", tr("toolbar.move_tooltip"))
        self._add_tool_button(layout, "rotate", "rotate_tool", tr("toolbar.rotate_tooltip"))
        self._add_tool_button(layout, "scale", "scale_tool", tr("toolbar.scale_tooltip"))
        self._add_tool_button(layout, "rotate_each", "rotate_each_tool", tr("toolbar.rotate_each_tooltip"))
        self._add_tool_button(layout, "scale_each", "scale_each_tool", tr("toolbar.scale_each_tooltip"))
        self._erase_btn = self._add_plain_button(
            layout, "erase_tool", tr("toolbar.erase_tooltip"), self.eraseRequested
        )
        layout.addWidget(self._separator())
        self._add_plain_button(
            layout, "zoom_extents_tool", tr("toolbar.zoom_extents_tooltip"), self.zoomExtentsRequested
        )
        self._add_plain_button(layout, "zoom_in_tool", tr("toolbar.zoom_in_tooltip"), self.zoomInRequested)
        self._add_plain_button(layout, "zoom_out_tool", tr("toolbar.zoom_out_tooltip"), self.zoomOutRequested)
        layout.addStretch(1)

        self.set_active_tool(None)
        self._erase_btn.setEnabled(False)

    def _add_tool_button(self, layout: qw.QHBoxLayout, key: str, icon_name: str, tooltip: str) -> None:
        btn = qw.QToolButton()
        btn.setObjectName("dxfToolBtn")
        btn.setIcon(icon_manager.get(icon_name, size=ICON_MD, color=UiColor.TEXT_MUTED))
        btn.setIconSize(qc.QSize(ICON_MD, ICON_MD))
        btn.setToolTip(tooltip)
        btn.setCheckable(True)
        btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked, k=key: self._on_tool_clicked(k, checked))
        layout.addWidget(btn)
        self._tool_buttons[key] = btn

    @staticmethod
    def _add_plain_button(
        layout: qw.QHBoxLayout, icon_name: str, tooltip: str, signal: qc.pyqtBoundSignal
    ) -> qw.QToolButton:
        btn = qw.QToolButton()
        btn.setObjectName("dxfToolBtn")
        btn.setIcon(icon_manager.get(icon_name, size=ICON_MD, color=UiColor.TEXT_MUTED))
        btn.setIconSize(qc.QSize(ICON_MD, ICON_MD))
        btn.setToolTip(tooltip)
        btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(signal.emit)
        layout.addWidget(btn)
        return btn

    @staticmethod
    def _separator() -> qw.QFrame:
        line = qw.QFrame()
        line.setObjectName("dxfToolbarSeparator")
        line.setFrameShape(qw.QFrame.Shape.VLine)
        return line

    def _on_tool_clicked(self, key: str, checked: bool) -> None:
        if key == "select":
            self.selectRequested.emit()
        elif checked:
            self._tool_signals[key].emit()
        else:
            self.selectRequested.emit()

    def set_active_tool(self, key: Optional[str]) -> None:
        self._active_key = key or "select"
        for name, btn in self._tool_buttons.items():
            checked = name == self._active_key
            btn.setChecked(checked)
            color = UiColor.ACCENT if checked else UiColor.TEXT_MUTED
            btn.setIcon(icon_manager.get(self._tool_icon_names[name], size=ICON_MD, color=color))

    def set_erase_enabled(self, enabled: bool) -> None:
        self._erase_btn.setEnabled(enabled)
