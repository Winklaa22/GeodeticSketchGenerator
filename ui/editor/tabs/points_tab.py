from __future__ import annotations

from core.config import PointsOptions
from ui.editor.tabs.base import LayeredOptionsTab

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_DIAMETER = "0.05"
EMPTY_DIAMETER_FALLBACK = "0.1"


class PointsTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = PointsOptions()

    def _build_fields(self) -> None:
        self.numbers_checkbox = self._add_check_field("Add numbers to points")
        self.font_size_input = self._add_decimal_field("Text size", DEFAULT_FONT_SIZE)
        self.diameter_input = self._add_decimal_field("Circle diameter", DEFAULT_DIAMETER)

    def get_options(self) -> PointsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        diameter = float((self.diameter_input.text() or EMPTY_DIAMETER_FALLBACK).replace(",", "."))
        return PointsOptions(
            numbers_enabled=self.numbers_checkbox.isChecked(),
            font_size=font_size,
            diameter=diameter,
        )

    def set_options(self, options: PointsOptions) -> None:
        self.numbers_checkbox.setChecked(options.numbers_enabled)
        self.font_size_input.setText(str(options.font_size))
        self.diameter_input.setText(str(options.diameter))
