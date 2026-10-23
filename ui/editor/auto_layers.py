from __future__ import annotations

from typing import Dict, Optional, Tuple

from core.auto_layers import AUTO_LAYER_RGB, AutoLayerGroup, auto_layer_group
from ui.i18n import tr

_NAME_KEYS: Dict[AutoLayerGroup, str] = {
    AutoLayerGroup.POINTS: "mode.points_label",
    AutoLayerGroup.MEASUREMENTS: "mode.measurements_label",
    AutoLayerGroup.PIPE: "mode.pipe_label",
    AutoLayerGroup.CABLE: "layer.auto_cable",
}


def auto_layer_for_mode(mode_key: str) -> Optional[Tuple[str, Tuple[int, int, int]]]:
    group = auto_layer_group(mode_key)
    if group is None:
        return None
    return tr(_NAME_KEYS[group]), AUTO_LAYER_RGB[group]
