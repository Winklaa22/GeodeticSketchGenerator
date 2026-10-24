from __future__ import annotations

from enum import Enum
from typing import Dict, Optional, Tuple


class AutoLayerGroup(Enum):
    POINTS = "points"
    MEASUREMENTS = "measurements"
    PIPE = "pipe"
    CABLE = "cable"


AUTO_LAYER_GROUP_BY_MODE_KEY: Dict[str, AutoLayerGroup] = {
    "points": AutoLayerGroup.POINTS,
    "measurements": AutoLayerGroup.MEASUREMENTS,
    "pipe": AutoLayerGroup.PIPE,
    "route": AutoLayerGroup.CABLE,
    "heights": AutoLayerGroup.CABLE,
    "cable": AutoLayerGroup.CABLE,
}

AUTO_LAYER_RGB: Dict[AutoLayerGroup, Tuple[int, int, int]] = {
    AutoLayerGroup.POINTS: (25, 55, 140),
    AutoLayerGroup.MEASUREMENTS: (255, 255, 255),
    AutoLayerGroup.PIPE: (255, 255, 255),
    AutoLayerGroup.CABLE: (229, 130, 138),
}


def auto_layer_group(mode_key: str) -> Optional[AutoLayerGroup]:
    return AUTO_LAYER_GROUP_BY_MODE_KEY.get(mode_key)
