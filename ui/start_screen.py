from __future__ import annotations

import os
import time
from typing import Optional

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import ProjectFileError
from core.project import PROJECT_FILE_FILTER, ProjectState, open_any, project_path_if_saved
from ui.assets import ICON_PATH
from ui.icons import icon_manager
from ui.recent_projects import add_recent_project, list_recent_projects, remove_recent_project
from ui.style import APP_STYLESHEET
from ui.theme import Color, ICON_SM, SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XL

_SETTINGS_ORG = "acsg"
_SETTINGS_APP = "acsg_pro"

_COLUMNS = ("File Type", "Name", "Location", "Last Opened", "Size")
_PATH_ROLE = Qt.ItemDataRole.UserRole


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.0f} KB"
    return f"{kb / 1024:.1f} MB"


def _format_last_opened(mtime: float) -> str:
    return time.strftime("%b %d, %Y", time.localtime(mtime))


class StartScreen(QMainWindow):

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Geodetic Sketch Generator")
        self.setWindowIcon(QIcon(ICON_PATH))
        self.resize(1000, 620)
        self.setMinimumSize(760, 480)
        self.settings = QSettings(_SETTINGS_ORG, _SETTINGS_APP)
        self._main_window: Optional[QMainWindow] = None

        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar())
        root.addWidget(self._build_main_area(), 1)

        self.setStyleSheet(APP_STYLESHEET)
        self._refresh_table()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("startSidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(SPACE_LG, SPACE_XL, SPACE_LG, SPACE_XL)
        layout.setSpacing(SPACE_SM)

        header = QHBoxLayout()
        header.setSpacing(SPACE_SM)
        header.addWidget(self._build_logo())
        title = QLabel("Geodetic Sketch\nGenerator")
        title.setObjectName("startTitle")
        header.addWidget(title, 1)
        layout.addLayout(header)
        layout.addSpacing(SPACE_LG)

        new_project_btn = self._make_button("New Project", "primary", self._on_new_project)
        new_project_btn.setIcon(icon_manager.get("new_project_icon", size=ICON_SM, color=Color.ACCENT))
        layout.addWidget(new_project_btn)
        layout.addWidget(self._make_button("Import…", "secondary", self._on_import))
        layout.addStretch(1)
        return sidebar

    @staticmethod
    def _build_logo() -> QLabel:
        logo = QLabel()
        logo.setObjectName("startLogo")
        pixmap = QPixmap(ICON_PATH)
        if not pixmap.isNull():
            logo.setPixmap(
                pixmap.scaled(
                    36, 36, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
            )
        return logo

    def _build_main_area(self) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)
        layout.setSpacing(SPACE_MD)

        heading = QLabel("Recent")
        heading.setObjectName("startHeading")
        layout.addWidget(heading)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setObjectName("startTable")
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setShowGrid(False)
        self.table.doubleClicked.connect(lambda _index: self._open_selected())
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No recent projects yet — start a new one, or import an existing file.")
        self.empty_label.setObjectName("startEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        self.remove_btn = self._make_button("Remove from list", "secondary", self._remove_selected)
        self.open_btn = self._make_button("Open", "primary", self._open_selected)
        button_row.addWidget(self.remove_btn)
        button_row.addWidget(self.open_btn)
        layout.addLayout(button_row)

        return wrapper

    @staticmethod
    def _make_button(text: str, variant: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("btn")
        btn.setProperty("variant", variant)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    def _refresh_table(self) -> None:
        paths = list_recent_projects(self.settings)
        self.table.setRowCount(len(paths))
        for row, path in enumerate(paths):
            self._fill_row(row, path)

        has_rows = bool(paths)
        self.table.setVisible(has_rows)
        self.empty_label.setVisible(not has_rows)
        self.open_btn.setEnabled(has_rows)
        self.remove_btn.setEnabled(has_rows)
        if has_rows:
            self.table.selectRow(0)

    def _fill_row(self, row: int, path: str) -> None:
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            stat = os.stat(path)
            size_text = _format_size(stat.st_size)
            last_opened = _format_last_opened(stat.st_mtime)
        except OSError:
            size_text = ""
            last_opened = ""
        values = ("Project", name, os.path.dirname(path), last_opened, size_text)
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setData(_PATH_ROLE, path)
            self.table.setItem(row, col, item)

    def _selected_path(self) -> Optional[str]:
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(_PATH_ROLE) if item is not None else None

    def _on_new_project(self) -> None:
        self._launch_editor(initial_state=None, project_path=None)

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import", "", f"{PROJECT_FILE_FILTER};;DXF Files (*.dxf);;Text Files (*.txt)"
        )
        if not path:
            return
        self._open_path(path)

    def _open_selected(self) -> None:
        path = self._selected_path()
        if path:
            self._open_path(path)

    def _open_path(self, path: str) -> None:
        try:
            state = open_any(path)
        except ProjectFileError as exc:
            QMessageBox.warning(self, "Could not open", str(exc))
            return
        project_path = project_path_if_saved(path)
        if project_path is not None:
            add_recent_project(self.settings, project_path)
        self._launch_editor(initial_state=state, project_path=project_path)

    def _remove_selected(self) -> None:
        path = self._selected_path()
        if not path:
            return
        remove_recent_project(self.settings, path)
        self._refresh_table()

    def _launch_editor(self, initial_state: Optional[ProjectState], project_path: Optional[str]) -> None:
        from ui.main_window import MainWindow

        self._main_window = MainWindow(initial_state=initial_state, project_path=project_path)
        self._main_window.show()
        self.close()
