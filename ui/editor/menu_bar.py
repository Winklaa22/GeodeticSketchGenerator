from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QSettings, Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence, QPixmap
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from ui.i18n import tr
from ui.recent_projects import list_recent_projects
from ui.theme import Color, ICON_SM, SPACE_MD, SPACE_SM
from ui.theme.assets import ICON_PATH
from ui.theme.icons import icon_manager
from ui.widgets import make_button, pin_menu_to_screen

LOGO_SIZE = 24


class MenuBar(QWidget):

    newProjectRequested = pyqtSignal()
    openProjectRequested = pyqtSignal()
    recentProjectRequested = pyqtSignal(str)
    saveProjectRequested = pyqtSignal()
    saveProjectAsRequested = pyqtSignal()
    renameProjectRequested = pyqtSignal()
    exportDxfRequested = pyqtSignal()
    tableStructureRequested = pyqtSignal()
    importTableTemplateRequested = pyqtSignal()
    exportTableTemplateRequested = pyqtSignal()
    closeProjectRequested = pyqtSignal()
    settingsRequested = pyqtSignal()
    undoRequested = pyqtSignal()
    redoRequested = pyqtSignal()
    editMenuAboutToShow = pyqtSignal()

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("topBar")
        self._settings = settings

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_MD, SPACE_SM, SPACE_MD, SPACE_SM)
        layout.setSpacing(SPACE_SM)
        layout.addWidget(self._build_logo())
        layout.addWidget(self._build_file_button())
        layout.addWidget(self._build_edit_button())
        layout.addStretch(1)

    @staticmethod
    def _build_logo() -> QLabel:
        logo = QLabel()
        logo.setObjectName("topBarLogo")
        pixmap = QPixmap(ICON_PATH)
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    LOGO_SIZE,
                    LOGO_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        return logo

    @staticmethod
    def _menu_button(text: str, object_name: str) -> tuple[QPushButton, QMenu]:
        button = make_button(text, "secondary")
        button.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        button.setIcon(icon_manager.get("menu_chevron", size=ICON_SM, color=Color.TEXT))
        menu = QMenu(button)
        menu.setObjectName(object_name)
        menu.aboutToShow.connect(lambda: pin_menu_to_screen(menu, button))
        button.setMenu(menu)
        return button, menu

    def _build_file_button(self) -> QPushButton:
        button, menu = self._menu_button(tr("menu.file"), "fileMenu")
        menu.addAction(tr("menu.new_project"), self.newProjectRequested.emit)
        menu.addAction(tr("menu.open_project"), self.openProjectRequested.emit)
        self._recent_menu = menu.addMenu(tr("menu.open_recent"))
        menu.aboutToShow.connect(self._refresh_recent_menu)
        menu.addSeparator()
        save_action = menu.addAction(tr("menu.save_project"), self.saveProjectRequested.emit)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        menu.addAction(tr("menu.save_project_as"), self.saveProjectAsRequested.emit)
        menu.addAction(tr("menu.rename_project"), self.renameProjectRequested.emit)
        menu.addAction(tr("menu.export_dxf"), self.exportDxfRequested.emit)
        menu.addSeparator()
        menu.addAction(tr("menu.table_structure"), self.tableStructureRequested.emit)
        menu.addAction(tr("menu.import_table_template"), self.importTableTemplateRequested.emit)
        menu.addAction(tr("menu.export_table_template"), self.exportTableTemplateRequested.emit)
        menu.addSeparator()
        menu.addAction(tr("common.settings"), self.settingsRequested.emit)
        menu.addSeparator()
        menu.addAction(tr("menu.close_project"), self.closeProjectRequested.emit)
        return button

    def _build_edit_button(self) -> QPushButton:
        button, menu = self._menu_button(tr("menu.edit"), "editMenu")
        self._undo_action = menu.addAction(tr("menu.undo"), self.undoRequested.emit)
        self._redo_action = menu.addAction(tr("menu.redo"), self.redoRequested.emit)
        menu.aboutToShow.connect(self.editMenuAboutToShow.emit)
        return button

    def _refresh_recent_menu(self) -> None:
        self._recent_menu.clear()
        paths = list_recent_projects(self._settings)
        if not paths:
            placeholder = self._recent_menu.addAction(tr("menu.no_recent_projects"))
            placeholder.setEnabled(False)
            return
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            self._recent_menu.addAction(
                name, lambda checked=False, p=path: self.recentProjectRequested.emit(p)
            )

    def set_undo_redo_enabled(self, can_undo: bool, can_redo: bool) -> None:
        self._undo_action.setEnabled(can_undo)
        self._redo_action.setEnabled(can_redo)
