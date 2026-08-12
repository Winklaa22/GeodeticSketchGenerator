"""PLINE drawing-mode strategy."""
from __future__ import annotations

from core.strategies.point_list_drawer import PointListDrawer


class PLineDrawer(PointListDrawer):
    """Draws a single AutoCAD PLINE through the selected points (2D only)."""

    command = "PLINE"
    include_height = False
