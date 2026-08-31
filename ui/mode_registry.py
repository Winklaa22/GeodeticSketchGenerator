from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Callable, Dict, Optional, Tuple, Type

from core.config import (
    CableOptions,
    HeightsOptions,
    MeasurementsOptions,
    PipeOptions,
    PointsOptions,
)
from core.draw_modes import DrawMode
from core.project import (
    CableState,
    HeightsState,
    LayerOnlyState,
    MeasurementsState,
    PipeState,
    PointsState,
)
from ui.tabs.base import LayeredOptionsTab, NoOptions
from ui.tabs.cable_tab import CableTab
from ui.tabs.heights_tab import HeightsTab
from ui.tabs.layer_only_tab import LayerOnlyTab
from ui.tabs.measurements_tab import MeasurementsTab
from ui.tabs.pipe_tab import PipeTab
from ui.tabs.points_tab import PointsTab


@dataclass(frozen=True)
class ModeSpec:
    key: str
    draw_mode: DrawMode
    icon: str
    title: str
    mode_label: str
    state_field: str
    state_cls: Type[Any]
    options_cls: Type[Any]
    config_field: Optional[str]
    tab_factory: Callable[[], LayeredOptionsTab]


MODE_SPECS: Tuple[ModeSpec, ...] = (
    ModeSpec(
        key="points",
        draw_mode=DrawMode.POINTS,
        icon="points_section",
        title="Points",
        mode_label="Points",
        state_field="points",
        state_cls=PointsState,
        options_cls=PointsOptions,
        config_field="points",
        tab_factory=PointsTab,
    ),
    ModeSpec(
        key="lines",
        draw_mode=DrawMode.LINES,
        icon="lines_section",
        title="Lines",
        mode_label="Lines",
        state_field="lines",
        state_cls=LayerOnlyState,
        options_cls=NoOptions,
        config_field=None,
        tab_factory=LayerOnlyTab,
    ),
    ModeSpec(
        key="plines",
        draw_mode=DrawMode.PLINES,
        icon="plines_section",
        title="PLines",
        mode_label="PLines",
        state_field="plines",
        state_cls=LayerOnlyState,
        options_cls=NoOptions,
        config_field=None,
        tab_factory=LayerOnlyTab,
    ),
    ModeSpec(
        key="3dpoly",
        draw_mode=DrawMode.POLY3D,
        icon="poly3d_section",
        title="3DPOLY",
        mode_label="3DPOLY",
        state_field="poly3d",
        state_cls=LayerOnlyState,
        options_cls=NoOptions,
        config_field=None,
        tab_factory=LayerOnlyTab,
    ),
    ModeSpec(
        key="heights",
        draw_mode=DrawMode.HEIGHTS,
        icon="heights_section",
        title="Heights",
        mode_label="Heights marks",
        state_field="heights",
        state_cls=HeightsState,
        options_cls=HeightsOptions,
        config_field="heights",
        tab_factory=HeightsTab,
    ),
    ModeSpec(
        key="cable",
        draw_mode=DrawMode.CABLE_MARKS,
        icon="cable_marks_section",
        title="Cable Marks",
        mode_label="Cable marks",
        state_field="cable",
        state_cls=CableState,
        options_cls=CableOptions,
        config_field="cable",
        tab_factory=CableTab,
    ),
    ModeSpec(
        key="pipe",
        draw_mode=DrawMode.PIPE,
        icon="pipe_section",
        title="Pipe",
        mode_label="Pipe",
        state_field="pipe",
        state_cls=PipeState,
        options_cls=PipeOptions,
        config_field="pipe",
        tab_factory=PipeTab,
    ),
    ModeSpec(
        key="measurements",
        draw_mode=DrawMode.MEASUREMENTS,
        icon="measurements_section",
        title="Measurements",
        mode_label="Measurements",
        state_field="measurements",
        state_cls=MeasurementsState,
        options_cls=MeasurementsOptions,
        config_field="measurements",
        tab_factory=MeasurementsTab,
    ),
)

SPEC_BY_KEY: Dict[str, ModeSpec] = {spec.key: spec for spec in MODE_SPECS}
SPEC_BY_DRAW_MODE: Dict[DrawMode, ModeSpec] = {spec.draw_mode: spec for spec in MODE_SPECS}


def state_from_tab(spec: ModeSpec, tab: LayeredOptionsTab) -> Any:
    return spec.state_cls(**asdict(tab.get_options()), layer_name=tab.get_layer_name())


def options_from_state(spec: ModeSpec, state: Any) -> Any:
    option_names = {field.name for field in fields(spec.options_cls)}
    payload = {name: value for name, value in asdict(state).items() if name in option_names}
    return spec.options_cls(**payload)
