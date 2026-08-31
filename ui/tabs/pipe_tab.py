from __future__ import annotations

from core.config import PipeOptions
from ui.tabs.base import LayeredOptionsTab

DEFAULT_WIDTH = "0.16"


class PipeTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = PipeOptions()

    def _build_fields(self) -> None:
        self.width_input = self._add_decimal_field("Pipe width", DEFAULT_WIDTH)

    def get_options(self) -> PipeOptions:
        return PipeOptions(width=float(self.width_input.text() or DEFAULT_WIDTH))

    def set_options(self, options: PipeOptions) -> None:
        self.width_input.setText(str(options.width))
