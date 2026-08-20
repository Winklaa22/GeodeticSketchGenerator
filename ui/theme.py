"""Design tokens for the "Nocturne" visual system.

Single source of truth for colors, radius and spacing so every widget and
the global stylesheet agree. The accent color is used as an outline / dot /
text color — it is deliberately almost never used as a fill (the one
sanctioned exception is the soft accent wash behind a selected
segmented-control / radio-card option).
"""
from __future__ import annotations


class Color:
    APP_BG = "#161826"
    SURFACE = "#1b1e2e"
    SURFACE_RAISED = "#20233a"
    SURFACE_SUNKEN = "#101220"
    SURFACE_HOVER = "#242842"

    BORDER = "#2b2e46"
    BORDER_STRONG = "#3a3e5c"

    TEXT = "#e8e9f3"
    TEXT_MUTED = "#8d90ad"
    TEXT_FAINT = "#5b5e78"

    ACCENT = "#9184d9"
    ACCENT_SOFT = "rgba(145, 132, 217, 0.14)"
    ACCENT_BORDER = "rgba(145, 132, 217, 0.55)"

    ERROR = "#e5828a"
    ERROR_BG = "rgba(197, 73, 80, 0.12)"
    ERROR_BORDER = "rgba(197, 73, 80, 0.45)"

    SUCCESS = "#7fcf9e"


RADIUS = 8
RADIUS_SM = 6
RADIUS_LG = 11
FONT_FAMILY = "Inter"
MONO_FONT_FAMILY = "JetBrains Mono"

# Compact spacing scale (0.7x of a conventional 8px-based scale).
SPACE_XS = 4
SPACE_SM = 6
SPACE_MD = 8
SPACE_LG = 11
SPACE_XL = 14
SPACE_XXL = 22

# Compact type scale, matched to the 0.7x spacing scale above.
TEXT_XS = 10
TEXT_SM = 11
TEXT_MD = 12
TEXT_LG = 14
TEXT_XL = 16

LEFT_COLUMN_WIDTH = 420
ICON_SM = 14
ICON_MD = 18
