from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from core.config import GenerationConfig
from core.draw_modes import DrawMode
from core.fonts import DEFAULT_FONT_ID
from models.point import Point
from ui.editor.mode_registry import MODE_SPECS, SPEC_BY_DRAW_MODE
from ui.editor.tabs.base import LayeredOptionsTab, SectionWidget
from ui.editor.tabs.delimiter_tab import DelimiterTab
from ui.editor.tabs.draw_tab import DrawTab
from ui.editor.tabs.layer_tab import LayerTab
from ui.i18n import tr
from ui.theme import SPACE_LG
from ui.widgets import Accordion, AccordionSection, DropZone, FileCard


class _PointFileSection(SectionWidget):

    def __init__(self, file_stack: QStackedWidget, delimiter_tab: DelimiterTab) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_LG)
        layout.addWidget(file_stack)
        layout.addWidget(delimiter_tab)
        self._delimiter_tab = delimiter_tab

    def is_modified(self) -> bool:
        return self._delimiter_tab.is_modified()


class SectionsPanel(QWidget):

    option_changed = pyqtSignal()
    layers_changed = pyqtSignal()
    delimiter_changed = pyqtSignal()
    file_requested = pyqtSignal()
    files_dropped = pyqtSignal(list)

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._sections: List[Tuple[AccordionSection, SectionWidget]] = []
        self._mode_section_keys: Dict[AccordionSection, str] = {}

        self._build_file_stack()
        self.delimiter_tab = DelimiterTab()
        self.draw_tab = DrawTab()
        self.layer_tab = LayerTab(settings)
        self.mode_tabs: Dict[str, LayeredOptionsTab] = {
            spec.key: spec.tab_factory() for spec in MODE_SPECS
        }

        self.accordion = Accordion()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.accordion)

        self._point_file_section = self._add_section(
            "point_file_section", tr("sections.point_file"),
            _PointFileSection(self.file_stack, self.delimiter_tab),
        )
        self._add_section("drawing_mode_section", tr("sections.drawing_mode"), self.draw_tab)
        self._layer_section = self._add_section("layer_section", tr("common.layer_field"), self.layer_tab)
        for spec in MODE_SPECS:
            section = self._add_section(spec.icon, spec.title, self.mode_tabs[spec.key])
            self._mode_section_keys[section] = spec.key

        self.sync_layer_dropdowns()
        self._wire_signals()

    def _build_file_stack(self) -> None:
        self.file_stack = QStackedWidget()
        self.drop_zone = DropZone()
        self.file_card = FileCard()
        self.file_stack.addWidget(self.drop_zone)
        self.file_stack.addWidget(self.file_card)

    def _add_section(self, icon: str, title: str, content: SectionWidget) -> AccordionSection:
        section = AccordionSection(icon, title, content)
        self.accordion.add_section(section)
        self._sections.append((section, content))
        return section

    def _wire_signals(self) -> None:
        self.drop_zone.fileRequested.connect(self.file_requested.emit)
        self.drop_zone.filesDropped.connect(self.files_dropped.emit)
        self.file_card.changeRequested.connect(self.file_requested.emit)

        self.delimiter_tab.swap_xy_toggled.connect(lambda _enabled: self.option_changed.emit())
        self.delimiter_tab.delimiter_changed.connect(self.delimiter_changed.emit)
        self.draw_tab.modes_changed.connect(self.option_changed.emit)
        self.layer_tab.layers_changed.connect(self._on_layers_changed)
        for tab in self.mode_tabs.values():
            tab.option_changed.connect(self.option_changed.emit)

    def _on_layers_changed(self) -> None:
        self.sync_layer_dropdowns()
        self.layers_changed.emit()

    def sync_layer_dropdowns(self) -> None:
        names = self.layer_tab.layer_names()
        default = self.layer_tab.default_layer_name()
        for tab in self.mode_tabs.values():
            tab.set_available_layers(names, default)

    def update_visibility(self, has_file: bool) -> None:
        checked_modes = set(self.draw_tab.mode_keys)
        self.delimiter_tab.setVisible(has_file)
        for section, _content in self._sections:
            if section is self._point_file_section:
                continue
            mode_key = self._mode_section_keys.get(section)
            if mode_key is not None:
                section.setVisible(has_file and mode_key in checked_modes)
            elif section is self._layer_section:
                section.setVisible(has_file and bool(checked_modes))
            else:
                section.setVisible(has_file)

    def refresh_modified_dots(self) -> None:
        for section, content in self._sections:
            section.set_modified(content.is_modified())

    def show_file(self, name: str, point_count: int, size_text: str) -> None:
        self.file_card.set_file(name, point_count, size_text)
        self.file_stack.setCurrentWidget(self.file_card)

    def show_drop_zone(self) -> None:
        self.file_stack.setCurrentWidget(self.drop_zone)

    def tab_for_mode(self, draw_mode: DrawMode) -> Optional[LayeredOptionsTab]:
        spec = SPEC_BY_DRAW_MODE.get(draw_mode)
        return self.mode_tabs[spec.key] if spec is not None else None

    def layer_name_for_mode(self, draw_mode: DrawMode) -> str:
        tab = self.tab_for_mode(draw_mode)
        return tab.get_layer_name() if tab is not None else self.layer_tab.default_layer_name()

    def build_generation_config(
        self,
        draw_mode: DrawMode,
        data: Dict[int, Point],
        quantum: float = 1.0,
        font_id: str = DEFAULT_FONT_ID,
        font_italic: bool = False,
        font_lineweight_mm: Optional[float] = None,
    ) -> GenerationConfig:
        layer_name = self.layer_name_for_mode(draw_mode)
        tab = self.tab_for_mode(draw_mode)
        options = {
            spec.config_field: self.mode_tabs[spec.key].get_options()
            for spec in MODE_SPECS
            if spec.config_field is not None
        }
        return GenerationConfig(
            layer_name=layer_name,
            draw_mode=draw_mode,
            selected_numbers=tuple(tab.get_selected_numbers(data)) if tab is not None else (),
            layer_rgb=self.layer_tab.get_rgb(layer_name),
            quantum=quantum,
            font_id=font_id,
            font_italic=font_italic,
            font_lineweight_mm=font_lineweight_mm,
            **options,
        )
