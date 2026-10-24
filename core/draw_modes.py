from __future__ import annotations

from enum import IntEnum


class DrawMode(IntEnum):
    POINTS = 1
    LINES = 2
    PLINES = 3
    POLY3D = 4
    HEIGHTS = 5
    CABLE_MARKS = 6
    PIPE = 7
    MEASUREMENTS = 8


CABLE_ROUTE_MODES = (DrawMode.LINES, DrawMode.PLINES, DrawMode.POLY3D)

CABLE_ROUTE_KINDS = {
    "lines": DrawMode.LINES,
    "plines": DrawMode.PLINES,
    "3dpoly": DrawMode.POLY3D,
}
DEFAULT_CABLE_ROUTE_KIND = "plines"


def cable_route_mode(kind: str) -> DrawMode:
    return CABLE_ROUTE_KINDS.get(kind, CABLE_ROUTE_KINDS[DEFAULT_CABLE_ROUTE_KIND])
