from __future__ import annotations

from core.config import PointsOptions
from ui.editor.tabs.base import LayeredOptionsTab
from ui.i18n import tr

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_CABINET_FONT_SIZE = "0.6"
DEFAULT_DIAMETER = "0.05"
EMPTY_DIAMETER_FALLBACK = "0.1"


class PointsTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = PointsOptions(numbers_enabled=True)

    def _build_fields(self) -> None:
        self.numbers_checkbox = self._add_check_field(tr("tabs.add_numbers_checkbox"), checked=True)
        self.font_size_input = self._add_decimal_field(tr("common.text_size"), DEFAULT_FONT_SIZE)
        self.cabinet_font_size_checkbox = self._add_check_field(tr("tabs.cabinet_font_size_enabled"))
        self.cabinet_font_size_input = self._add_decimal_field(
            tr("tabs.cabinet_font_size"), DEFAULT_CABINET_FONT_SIZE
        )
        self.diameter_input = self._add_decimal_field(tr("tabs.circle_diameter"), DEFAULT_DIAMETER)

        self.numbers_checkbox.toggled.connect(self._update_font_field_visibility)
        self.cabinet_font_size_checkbox.toggled.connect(self._update_font_field_visibility)
        self._update_font_field_visibility()

    def _update_font_field_visibility(self) -> None:
        numbers_enabled = self.numbers_checkbox.isChecked()
        self.font_size_input.parentWidget().setVisible(numbers_enabled)
        self.cabinet_font_size_checkbox.setVisible(numbers_enabled)
        self.cabinet_font_size_input.parentWidget().setVisible(
            numbers_enabled and self.cabinet_font_size_checkbox.isChecked()
        )

    def get_options(self) -> PointsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        cabinet_font_size = float(self.cabinet_font_size_input.text() or DEFAULT_CABINET_FONT_SIZE)
        diameter = float((self.diameter_input.text() or EMPTY_DIAMETER_FALLBACK).replace(",", "."))
        return PointsOptions(
            numbers_enabled=self.numbers_checkbox.isChecked(),
            font_size=font_size,
            cabinet_font_size_enabled=self.cabinet_font_size_checkbox.isChecked(),
            cabinet_font_size=cabinet_font_size,
            diameter=diameter,
        )

    def set_options(self, options: PointsOptions) -> None:
        self.numbers_checkbox.setChecked(options.numbers_enabled)
        self.font_size_input.setText(str(options.font_size))
        self.cabinet_font_size_checkbox.setChecked(options.cabinet_font_size_enabled)
        self.cabinet_font_size_input.setText(str(options.cabinet_font_size))
        self.diameter_input.setText(str(options.diameter))
