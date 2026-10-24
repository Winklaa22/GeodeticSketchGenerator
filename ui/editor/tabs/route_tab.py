from __future__ import annotations

from core.config import CableRouteOptions
from core.draw_modes import CABLE_ROUTE_KINDS, DEFAULT_CABLE_ROUTE_KIND, DrawMode, cable_route_mode
from ui.editor.tabs.base import LayeredOptionsTab
from ui.i18n import tr
from ui.widgets import Dropdown

_KIND_LABEL_KEYS = {
    "lines": "mode.lines_label",
    "plines": "mode.plines_label",
    "3dpoly": "mode.poly3d_label",
}


class CableRouteTab(LayeredOptionsTab):

    DEFAULT_OPTIONS = CableRouteOptions()

    def _build_fields(self) -> None:
        self.kind_control = Dropdown()
        self.kind_control.set_items([(kind, tr(_KIND_LABEL_KEYS[kind])) for kind in CABLE_ROUTE_KINDS])
        self.kind_control.set_current_key(DEFAULT_CABLE_ROUTE_KIND)
        self.kind_control.currentIndexChanged.connect(lambda _index: self.option_changed.emit())
        self._add_field(tr("tabs.route_kind"), self.kind_control)

    @property
    def draw_mode(self) -> DrawMode:
        return cable_route_mode(self.kind_control.current_key() or DEFAULT_CABLE_ROUTE_KIND)

    def get_options(self) -> CableRouteOptions:
        return CableRouteOptions(kind=self.kind_control.current_key() or DEFAULT_CABLE_ROUTE_KIND)

    def set_options(self, options: CableRouteOptions) -> None:
        self.kind_control.set_current_key(options.kind if options.kind in CABLE_ROUTE_KINDS else DEFAULT_CABLE_ROUTE_KIND)
