from __future__ import annotations

from core.config import HeightsOptions
from ui.editor.tabs.base import LayeredOptionsTab
from ui.i18n import tr

DEFAULT_FONT_SIZE = "0.6"


class HeightsTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = HeightsOptions()

    def _build_fields(self) -> None:
        self.font_size_input = self._add_decimal_field(tr("common.text_size"), DEFAULT_FONT_SIZE)

    def get_options(self) -> HeightsOptions:
        font_size = float(self.font_size_input.text() or DEFAULT_FONT_SIZE)
        return HeightsOptions(font_size=font_size)

    def set_options(self, options: HeightsOptions) -> None:
        self.font_size_input.setText(str(options.font_size))
