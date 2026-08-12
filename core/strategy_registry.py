from __future__ import annotations

from typing import Callable, Dict

from core.draw_modes import DrawMode, ScriptDrawer
from core.strategies.cable_strategy import CableDrawer
from core.strategies.heights_strategy import HeightsDrawer
from core.strategies.lines_strategy import LinesDrawer
from core.strategies.pline_strategy import PLineDrawer
from core.strategies.points_strategy import PointsDrawer
from core.strategies.poly3d_strategy import Poly3DDrawer

_STRATEGIES: Dict[DrawMode, Callable[[], ScriptDrawer]] = {
    DrawMode.POINTS: PointsDrawer,
    DrawMode.LINES: LinesDrawer,
    DrawMode.PLINES: PLineDrawer,
    DrawMode.POLY3D: Poly3DDrawer,
    DrawMode.HEIGHTS: HeightsDrawer,
    DrawMode.CABLE_MARKS: CableDrawer,
}


def get_strategy(draw_mode: DrawMode) -> ScriptDrawer:
    """Resolves the ScriptDrawer strategy registered for `draw_mode`."""
    try:
        return _STRATEGIES[draw_mode]()
    except KeyError as exc:
        raise ValueError(f"Unsupported draw mode: {draw_mode!r}") from exc
