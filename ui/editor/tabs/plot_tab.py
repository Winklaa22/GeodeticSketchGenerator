from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.plot import (
    COLOR_MODE_COLOR,
    COLOR_MODE_MONOCHROME,
    DEFAULT_SCALE_DENOMINATOR,
    PAGE_SIZES,
    SCALE_MODE_FIT,
    SCALE_MODE_FIXED,
    SCALE_PRESETS,
    PlotOptions,
)
from ui.editor.tabs.base import SectionWidget
from ui.widgets import (
    Dropdown,
    SectionColumn,
    SegmentedControl,
    decimal_validator,
    make_button,
    make_field,
    styled_line_edit,
)

DEFAULT_MARGIN = "10"
DEFAULT_MIN_LINEWEIGHT = "0.13"
DEFAULT_ROTATION = "0"
CUSTOM_SCALE_KEY = "custom"
FIT_SCALE_KEY = "fit"

_ORIENTATION_OPTIONS = [("landscape", "Landscape"), ("portrait", "Portrait")]
_COLOR_OPTIONS = [(COLOR_MODE_COLOR, "Color"), (COLOR_MODE_MONOCHROME, "Monochrome")]


def _scale_items():
    items = [(str(value), f"1:{value}") for value in SCALE_PRESETS]
    items.append((CUSTOM_SCALE_KEY, "Custom…"))
    items.append((FIT_SCALE_KEY, "Fit to page"))
    return items


class PlotTab(SectionWidget):

    optionsChanged = pyqtSignal()
    exportRequested = pyqtSignal()
    centerRequested = pyqtSignal()

    DEFAULT_OPTIONS = PlotOptions()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        column = SectionColumn(self)

        self.page_dropdown = Dropdown()
        self.page_dropdown.set_items([(spec.key, spec.label) for spec in PAGE_SIZES])
        self.page_dropdown.set_current_key(self.DEFAULT_OPTIONS.page_key)
        column.addWidget(make_field("Paper size", self.page_dropdown))

        self.orientation_control = SegmentedControl(_ORIENTATION_OPTIONS)
        column.addWidget(make_field("Orientation", self.orientation_control))

        self.scale_dropdown = Dropdown()
        self.scale_dropdown.set_items(_scale_items())
        self.scale_dropdown.set_current_key(str(DEFAULT_SCALE_DENOMINATOR))
        column.addWidget(make_field("Plot scale", self.scale_dropdown))

        self.custom_scale_input = styled_line_edit(str(DEFAULT_SCALE_DENOMINATOR))
        self.custom_scale_input.setValidator(QIntValidator(1, 1000000))
        self._custom_scale_field = make_field("Custom scale 1:", self.custom_scale_input)
        self._custom_scale_field.setVisible(False)
        column.addWidget(self._custom_scale_field)

        self.margin_input = styled_line_edit(DEFAULT_MARGIN)
        self.margin_input.setValidator(decimal_validator(0.0, 100.0, 1))
        column.addWidget(make_field("Margins (mm)", self.margin_input))

        self.rotation_input = styled_line_edit(DEFAULT_ROTATION)
        self.rotation_input.setValidator(decimal_validator(-180.0, 180.0, 2))
        column.addWidget(make_field("Rotation (°)", self.rotation_input))

        self.color_control = SegmentedControl(_COLOR_OPTIONS)
        column.addWidget(make_field("Plot style", self.color_control))

        self.min_lineweight_input = styled_line_edit(DEFAULT_MIN_LINEWEIGHT)
        self.min_lineweight_input.setValidator(decimal_validator(0.0, 5.0, 2))
        column.addWidget(make_field("Minimum lineweight (mm)", self.min_lineweight_input))

        self.coverage_label = QLabel("")
        self.coverage_label.setObjectName("previewMeta")
        self.coverage_label.setWordWrap(True)
        column.addWidget(self.coverage_label)

        column.addLayout(self._build_actions())
        column.addStretch(1)

        self._wire_signals()

    def _build_actions(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.center_button = make_button(
            "Center on drawing", "secondary", lambda: self.centerRequested.emit()
        )
        self.export_button = make_button(
            "Export PDF", "primary", lambda: self.exportRequested.emit()
        )
        row.addWidget(self.center_button)
        row.addStretch(1)
        row.addWidget(self.export_button)
        return row

    def _wire_signals(self) -> None:
        self.page_dropdown.currentIndexChanged.connect(lambda _i: self.optionsChanged.emit())
        self.orientation_control.currentChanged.connect(lambda _k: self.optionsChanged.emit())
        self.scale_dropdown.currentIndexChanged.connect(lambda _i: self._on_scale_changed())
        self.custom_scale_input.textChanged.connect(lambda _t: self.optionsChanged.emit())
        self.margin_input.textChanged.connect(lambda _t: self.optionsChanged.emit())
        self.rotation_input.textChanged.connect(lambda _t: self.optionsChanged.emit())
        self.color_control.currentChanged.connect(lambda _k: self.optionsChanged.emit())
        self.min_lineweight_input.textChanged.connect(lambda _t: self.optionsChanged.emit())

    def _on_scale_changed(self) -> None:
        self._sync_custom_field()
        self.optionsChanged.emit()

    def _sync_custom_field(self) -> None:
        self._custom_scale_field.setVisible(self.scale_dropdown.current_key() == CUSTOM_SCALE_KEY)

    def _denominator(self) -> int:
        key = self.scale_dropdown.current_key()
        if key == CUSTOM_SCALE_KEY:
            text = self.custom_scale_input.text().strip()
            return int(text) if text.isdigit() and int(text) > 0 else DEFAULT_SCALE_DENOMINATOR
        if key == FIT_SCALE_KEY:
            return DEFAULT_SCALE_DENOMINATOR
        return int(key) if key.isdigit() else DEFAULT_SCALE_DENOMINATOR

    @staticmethod
    def _decimal(text: str, fallback: str) -> float:
        return float((text or fallback).replace(",", ".") or fallback)

    def get_options(self) -> PlotOptions:
        return PlotOptions(
            page_key=self.page_dropdown.current_key(),
            landscape=self.orientation_control.current() != "portrait",
            scale_mode=(
                SCALE_MODE_FIT
                if self.scale_dropdown.current_key() == FIT_SCALE_KEY
                else SCALE_MODE_FIXED
            ),
            scale_denominator=self._denominator(),
            margin_mm=self._decimal(self.margin_input.text(), DEFAULT_MARGIN),
            color_mode=self.color_control.current() or COLOR_MODE_COLOR,
            min_lineweight_mm=self._decimal(
                self.min_lineweight_input.text(), DEFAULT_MIN_LINEWEIGHT
            ),
        )

    def get_rotation(self) -> float:
        return self._decimal(self.rotation_input.text(), DEFAULT_ROTATION)

    def set_rotation(self, rotation: float) -> None:
        self.rotation_input.blockSignals(True)
        self.rotation_input.setText(f"{rotation:g}")
        self.rotation_input.blockSignals(False)

    def set_options(self, options: PlotOptions) -> None:
        for widget in (
            self.page_dropdown,
            self.scale_dropdown,
            self.custom_scale_input,
            self.margin_input,
            self.min_lineweight_input,
        ):
            widget.blockSignals(True)
        self.page_dropdown.set_current_key(options.page_key)
        self.orientation_control.setCurrent(
            "landscape" if options.landscape else "portrait"
        )
        if options.scale_mode == SCALE_MODE_FIT:
            self.scale_dropdown.set_current_key(FIT_SCALE_KEY)
        elif str(options.scale_denominator) in {str(value) for value in SCALE_PRESETS}:
            self.scale_dropdown.set_current_key(str(options.scale_denominator))
        else:
            self.scale_dropdown.set_current_key(CUSTOM_SCALE_KEY)
        self.custom_scale_input.setText(str(options.scale_denominator))
        self.margin_input.setText(str(options.margin_mm))
        self.color_control.setCurrent(options.color_mode)
        self.min_lineweight_input.setText(str(options.min_lineweight_mm))
        for widget in (
            self.page_dropdown,
            self.scale_dropdown,
            self.custom_scale_input,
            self.margin_input,
            self.min_lineweight_input,
        ):
            widget.blockSignals(False)
        self._sync_custom_field()

    def set_coverage_text(self, text: str) -> None:
        self.coverage_label.setText(text)

    def set_export_enabled(self, enabled: bool) -> None:
        self.export_button.setEnabled(enabled)

    def is_modified(self) -> bool:
        return self.get_options() != self.DEFAULT_OPTIONS
