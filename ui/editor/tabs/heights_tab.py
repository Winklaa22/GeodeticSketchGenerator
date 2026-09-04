from __future__ import annotations

from core.config import HeightsOptions
from ui.editor.tabs.base import LayeredOptionsTab
from ui.i18n import tr

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_FREQUENCY = "5"


class HeightsTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = HeightsOptions()

    def _build_fields(self) -> None:
        self.font_size_input = self._add_decimal_field(tr("common.text_size"), DEFAULT_FONT_SIZE)
        self.frequency_input = self._add_int_field(tr("tabs.heights_frequency"), DEFAULT_FREQUENCY)

    def get_options(self) -> HeightsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        frequency = int(self.frequency_input.text() or DEFAULT_FREQUENCY)
        return HeightsOptions(font_size=font_size, frequency=frequency)

    def set_options(self, options: HeightsOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
        self.frequency_input.setText(str(options.frequency))
