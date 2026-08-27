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
