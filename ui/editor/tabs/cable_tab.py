from __future__ import annotations

from core.config import CableOptions
from ui.editor.tabs.base import LayeredOptionsTab
from ui.i18n import tr

DEFAULT_FONT_SIZE = "0.6"
DEFAULT_FREQUENCY = "5"
DEFAULT_MARKS_TEXT = "eN"


class CableTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = CableOptions()

    def _build_fields(self) -> None:
        self.font_size_input = self._add_decimal_field(tr("common.text_size"), DEFAULT_FONT_SIZE)
        self.frequency_input = self._add_int_field(tr("tabs.cable_frequency"), DEFAULT_FREQUENCY)
        self.marks_text_input = self._add_text_field(tr("tabs.cable_marks_text"), DEFAULT_MARKS_TEXT)

    def get_options(self) -> CableOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        frequency = int(self.frequency_input.text() or DEFAULT_FREQUENCY)
        marks_text = self.marks_text_input.text() or DEFAULT_MARKS_TEXT
        return CableOptions(font_size=font_size, frequency=frequency, marks_text=marks_text)

    def set_options(self, options: CableOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
        self.frequency_input.setText(str(options.frequency))
        self.marks_text_input.setText(options.marks_text)
