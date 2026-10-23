from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import QSettings, Qt, pyqtBoundSignal, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence, QPixmap, QShortcut
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QWidget

from ui.i18n import tr
from ui.recent_projects import list_recent_projects
from ui.theme import Color, ICON_SM, SPACE_MD, SPACE_SM
from ui.theme.assets import ICON_PATH
from ui.theme.icons import icon_manager
from ui.widgets import make_button, pin_menu_to_screen

LOGO_SIZE = 24

SHORTCUT_NEW_PROJECT = "Ctrl+N"
SHORTCUT_OPEN_PROJECT = "Ctrl+O"
SHORTCUT_SAVE_PROJECT = "Ctrl+S"
SHORTCUT_SAVE_PROJECT_AS = "Ctrl+Shift+S"
SHORTCUT_RENAME_PROJECT = "F2"
SHORTCUT_EXPORT_DXF = "Ctrl+E"
SHORTCUT_TABLE_STRUCTURE = "Ctrl+T"
SHORTCUT_SETTINGS = "Ctrl+,"
SHORTCUT_CLOSE_PROJECT = "Ctrl+W"
SHORTCUT_UNDO = "Ctrl+Z"
SHORTCUT_REDO = "Ctrl+Y"


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
        menu.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
        menu.setToolTipsVisible(True)
        menu.aboutToShow.connect(lambda: pin_menu_to_screen(menu, button))
        button.setMenu(menu)
        return button, menu

    def _build_file_button(self) -> QPushButton:
        button, menu = self._menu_button(tr("menu.file"), "fileMenu")
        self._add_action(menu, tr("menu.new_project"), self.newProjectRequested, SHORTCUT_NEW_PROJECT)
        self._add_action(menu, tr("menu.open_project"), self.openProjectRequested, SHORTCUT_OPEN_PROJECT)
        self._recent_menu = menu.addMenu(tr("menu.open_recent"))
        menu.aboutToShow.connect(self._refresh_recent_menu)
        menu.addSeparator()
        self._add_action(menu, tr("menu.save_project"), self.saveProjectRequested, SHORTCUT_SAVE_PROJECT)
        self._add_action(menu, tr("menu.save_project_as"), self.saveProjectAsRequested, SHORTCUT_SAVE_PROJECT_AS)
        self._add_action(menu, tr("menu.rename_project"), self.renameProjectRequested, SHORTCUT_RENAME_PROJECT)
        self._add_action(menu, tr("menu.export_dxf"), self.exportDxfRequested, SHORTCUT_EXPORT_DXF)
        menu.addSeparator()
        self._add_action(menu, tr("menu.table_structure"), self.tableStructureRequested, SHORTCUT_TABLE_STRUCTURE)
        self._add_action(menu, tr("menu.import_table_template"), self.importTableTemplateRequested)
        self._add_action(menu, tr("menu.export_table_template"), self.exportTableTemplateRequested)
        menu.addSeparator()
        self._add_action(menu, tr("common.settings"), self.settingsRequested, SHORTCUT_SETTINGS)
        menu.addSeparator()
        self._add_action(menu, tr("menu.close_project"), self.closeProjectRequested, SHORTCUT_CLOSE_PROJECT)
        return button

    def _add_action(
        self, menu: QMenu, text: str, signal: pyqtBoundSignal, shortcut: Optional[str] = None
    ) -> QAction:
        action = menu.addAction(text, signal.emit)
        if shortcut is not None:
            self._show_shortcut_on_hover(action, shortcut)
            key = QShortcut(QKeySequence(shortcut), self)
            key.setContext(Qt.ShortcutContext.WindowShortcut)
            key.activated.connect(action.trigger)
        return action

    @staticmethod
    def _show_shortcut_on_hover(action: QAction, shortcut: str) -> None:
        native = QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)
        action.setToolTip(f"{action.text().rstrip('…')} ({native})")

    def _build_edit_button(self) -> QPushButton:
        button, menu = self._menu_button(tr("menu.edit"), "editMenu")
        self._undo_action = menu.addAction(tr("menu.undo"), self.undoRequested.emit)
        self._redo_action = menu.addAction(tr("menu.redo"), self.redoRequested.emit)
        self._show_shortcut_on_hover(self._undo_action, SHORTCUT_UNDO)
        self._show_shortcut_on_hover(self._redo_action, SHORTCUT_REDO)
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
