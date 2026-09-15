from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtCore as qc, QtWidgets as qw

from ui.i18n import tr
from ui.theme import Color as UiColor, ICON_SM, SPACE_XS
from ui.theme.icons import icon_manager

_NAME_MAX_WIDTH = 160


class SheetTabBar(qw.QWidget):

    modelActivated = qc.pyqtSignal()
    sheetActivated = qc.pyqtSignal(int)
    addRequested = qc.pyqtSignal()
    renameRequested = qc.pyqtSignal(int)
    duplicateRequested = qc.pyqtSignal(int)
    deleteRequested = qc.pyqtSignal(int)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sheetTabBar")
        self._layout = qw.QHBoxLayout(self)
        self._layout.setContentsMargins(0, SPACE_XS, 0, 0)
        self._layout.setSpacing(SPACE_XS)
        self.refresh([], None)

    def refresh(self, names: Sequence[str], active: Optional[int]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        model_tab = self._make_tab(tr("sheet_tabs.model"), active is None)
        model_tab.setToolTip(tr("sheet_tabs.model_tooltip"))
        model_tab.clicked.connect(lambda: self.modelActivated.emit())
        self._layout.addWidget(model_tab)

        for index, name in enumerate(names):
            tab = self._make_tab(name, index == active)
            tab.setToolTip(tr("sheet_tabs.sheet_tooltip", name=name))
            tab.clicked.connect(lambda _checked=False, i=index: self.sheetActivated.emit(i))
            tab.setContextMenuPolicy(qc.Qt.ContextMenuPolicy.CustomContextMenu)
            tab.customContextMenuRequested.connect(
                lambda pos, i=index, t=tab: self._show_menu(t, pos, i)
            )
            self._layout.addWidget(tab)

        add_tab = qw.QToolButton()
        add_tab.setObjectName("sheetTabAdd")
        add_tab.setIcon(icon_manager.get("sheet_add", size=ICON_SM, color=UiColor.TEXT_MUTED))
        add_tab.setIconSize(qc.QSize(ICON_SM, ICON_SM))
        add_tab.setToolTip(tr("sheet_tabs.add_sheet_tooltip"))
        add_tab.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        add_tab.clicked.connect(lambda: self.addRequested.emit())
        self._layout.addWidget(add_tab)
        self._layout.addStretch(1)

    def _make_tab(self, text: str, active: bool) -> qw.QToolButton:
        tab = qw.QToolButton()
        tab.setObjectName("sheetTab")
        tab.setProperty("active", "true" if active else "false")
        tab.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        metrics = tab.fontMetrics()
        tab.setText(metrics.elidedText(text, qc.Qt.TextElideMode.ElideRight, _NAME_MAX_WIDTH))
        return tab

    def _show_menu(self, tab: qw.QToolButton, pos: qc.QPoint, index: int) -> None:
        menu = qw.QMenu(self)
        menu.addAction(tr("sheet_tabs.rename_ellipsis"), lambda: self.renameRequested.emit(index))
        menu.addAction(tr("common.duplicate"), lambda: self.duplicateRequested.emit(index))
        menu.addSeparator()
        menu.addAction(tr("common.delete"), lambda: self.deleteRequested.emit(index))
        menu.exec(tab.mapToGlobal(pos))


class SheetList(qw.QWidget):

    activated = qc.pyqtSignal(int)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._layout = qw.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(SPACE_XS)
        self._rows: List[qw.QToolButton] = []

    def refresh(self, names: Sequence[str], active: Optional[int]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._rows = []

        if not names:
            empty = qw.QLabel(tr("sheet_tabs.empty_hint"))
            empty.setObjectName("previewMeta")
            empty.setWordWrap(True)
            self._layout.addWidget(empty)
            return

        for index, name in enumerate(names):
            row = qw.QToolButton()
            row.setObjectName("sheetRow")
            row.setProperty("active", "true" if index == active else "false")
            row.setText(name)
            row.setCursor(qc.Qt.CursorShape.PointingHandCursor)
            row.setToolButtonStyle(qc.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            row.setSizePolicy(qw.QSizePolicy.Policy.Expanding, qw.QSizePolicy.Policy.Fixed)
            row.clicked.connect(lambda _checked=False, i=index: self.activated.emit(i))
            self._layout.addWidget(row)
            self._rows.append(row)
