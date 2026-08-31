from __future__ import annotations

from core.config import MeasurementsOptions
from ui.tabs.base import LayeredOptionsTab

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_OFFSET = "0.3"


class MeasurementsTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = MeasurementsOptions()

    def _build_fields(self) -> None:
        self.font_size_input = self._add_decimal_field("Text size", DEFAULT_FONT_SIZE)
        self.offset_input = self._add_decimal_field("Offset from line", DEFAULT_OFFSET)

    def get_options(self) -> MeasurementsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        offset = float((self.offset_input.text() or DEFAULT_OFFSET).replace(",", "."))
        return MeasurementsOptions(font_size=font_size, offset=offset)

    def set_options(self, options: MeasurementsOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
        self.offset_input.setText(str(options.offset))
