from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import ProjectFileError
from core.project import TABLE_TEMPLATE_FILE_FILTER, load_table_template_file
from core.table_template import TableTemplate
from ui.editor.table_structure_dialog import TableStructureDialog
from ui.global_settings import (
    default_table_enabled,
    default_table_template,
    has_custom_default_table,
    set_default_table_enabled,
    set_default_table_template,
)
from ui.theme import SPACE_LG, SPACE_MD, SPACE_SM, SPACE_XL
from ui.theme.style import APP_STYLESHEET
from ui.widgets import CheckField, SectionColumn, SidebarNav, make_button


class SettingsDialog(QDialog):

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setStyleSheet(APP_STYLESHEET)
        self.resize(640, 420)
        self._settings = settings
        self._template = default_table_template(settings)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        self._stack = QStackedWidget()
        content.addWidget(self._build_sidebar())
        content.addWidget(self._stack, 1)
        outer.addLayout(content, 1)
        outer.addWidget(self._build_footer())

        self._refresh_status()
        self._sync_enabled_state()

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("settingsSidebar")
        sidebar.setFixedWidth(190)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(SPACE_LG, SPACE_XL, SPACE_LG, SPACE_XL)
        layout.setSpacing(SPACE_SM)

        pages = [("table", "Default Table", "table_section", self._build_table_section())]
        self._nav = SidebarNav([(key, label, icon) for key, label, icon, _widget in pages])
        indexes = {key: self._stack.addWidget(widget) for key, _label, _icon, widget in pages}
        self._nav.currentChanged.connect(lambda key: self._stack.setCurrentIndex(indexes[key]))
        layout.addWidget(self._nav)
        layout.addStretch(1)
        return sidebar

    def _build_footer(self) -> QWidget:
        footer = QWidget()
        footer.setObjectName("settingsFooter")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.accept)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        return footer

    def _build_table_section(self) -> QWidget:
        page = QWidget()
        column = SectionColumn(page)
        column.setContentsMargins(SPACE_XL, SPACE_XL, SPACE_XL, SPACE_XL)

        heading = QLabel("Default table for new projects")
        heading.setObjectName("startHeading")
        column.addWidget(heading)

        self._enabled_check = CheckField("New projects start with a default table")
        self._enabled_check.setChecked(default_table_enabled(self._settings))
        self._enabled_check.toggled.connect(self._on_enabled_toggled)
        column.addWidget(self._enabled_check)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        column.addWidget(self._status_label)

        actions = QHBoxLayout()
        actions.setSpacing(SPACE_SM)
        self._import_button = make_button("Import…", "secondary", self._on_import)
        actions.addWidget(self._import_button)
        self._create_button = make_button("Create / Edit…", "secondary", self._on_create)
        actions.addWidget(self._create_button)
        actions.addStretch(1)
        column.addLayout(actions)

        column.addStretch(1)
        return page

    def _on_enabled_toggled(self, checked: bool) -> None:
        set_default_table_enabled(self._settings, checked)
        self._sync_enabled_state()

    def _sync_enabled_state(self) -> None:
        enabled = self._enabled_check.isChecked()
        self._import_button.setEnabled(enabled)
        self._create_button.setEnabled(enabled)

    def _refresh_status(self) -> None:
        rows, cols = len(self._template.rows), len(self._template.columns)
        self._status_label.setText(f"Current default table: {rows} row(s) × {cols} column(s).")

    def _on_import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Table Template", "", TABLE_TEMPLATE_FILE_FILTER)
        if not path:
            return
        try:
            template = load_table_template_file(path)
        except ProjectFileError as exc:
            QMessageBox.warning(self, "Import Table Template", str(exc))
            return
        self._apply_template(template)

    def _on_create(self) -> None:
        seed = self._template if has_custom_default_table(self._settings) else TableTemplate(
            columns=[], rows=[], cells=[]
        )
        dialog = TableStructureDialog(seed, self)
        if dialog.exec():
            self._apply_template(dialog.result_template())

    def _apply_template(self, template: TableTemplate) -> None:
        self._template = template
        set_default_table_template(self._settings, template)
        self._refresh_status()
