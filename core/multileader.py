from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Optional, Sequence, Tuple


MULTILEADER_APPID = "GSG_MLEADER"
_METADATA_VERSION = "1"


@dataclass(frozen=True)
class MultileaderSpec:
    tip: Tuple[float, float]
    landing: Optional[Tuple[float, float]]
    text_position: Tuple[float, float]
    text: str
    height: float = 0.6
    line_type: str = "straight"
    arrowhead: str = "closed"
    attachment: str = "left"
    landing_enabled: bool = True
    gap: float = 0.18
    layer: str = "0"
    identifier: str = ""

    def normalized(self) -> "MultileaderSpec":
        line_type = self.line_type if self.line_type in {"straight", "spline"} else "straight"
        arrowhead = self.arrowhead if self.arrowhead in {"closed", "open", "dot"} else "closed"
        attachment = self.attachment if self.attachment in {"left", "right"} else "left"
        return MultileaderSpec(
            tip=(float(self.tip[0]), float(self.tip[1])),
            landing=(float(self.landing[0]), float(self.landing[1])) if self.landing is not None else None,
            text_position=(float(self.text_position[0]), float(self.text_position[1])),
            text=str(self.text),
            height=max(float(self.height), 0.01),
            line_type=line_type,
            arrowhead=arrowhead,
            attachment=attachment,
            landing_enabled=bool(self.landing_enabled and self.landing is not None),
            gap=max(float(self.gap), 0.0),
            layer=str(self.layer),
            identifier=self.identifier or uuid.uuid4().hex,
        )

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "MultileaderSpec":
        landing = payload.get("landing")
        return cls(
            tip=tuple(payload["tip"]),
            landing=tuple(landing) if landing is not None else None,
            text_position=tuple(payload["text_position"]),
            text=str(payload.get("text", "")),
            height=float(payload.get("height", 0.6)),
            line_type=str(payload.get("line_type", "straight")),
            arrowhead=str(payload.get("arrowhead", "closed")),
            attachment=str(payload.get("attachment", "left")),
            landing_enabled=bool(payload.get("landing_enabled", landing is not None)),
            gap=float(payload.get("gap", 0.18)),
            layer=str(payload.get("layer", "0")),
            identifier=str(payload.get("identifier", "")),
        ).normalized()


def text_connection(spec: MultileaderSpec) -> Tuple[float, float]:
    direction = -1.0 if spec.attachment == "left" else 1.0
    return spec.text_position[0] + direction * spec.gap, spec.text_position[1]


def leader_points(spec: MultileaderSpec) -> Tuple[Tuple[float, float], ...]:
    end = text_connection(spec)
    if spec.landing_enabled and spec.landing is not None:
        return spec.tip, spec.landing, end
    return spec.tip, end


def spline_fit_points(spec: MultileaderSpec) -> Tuple[Tuple[float, float], ...]:
    route = leader_points(spec)
    if len(route) > 2:
        return route
    start, end = route
    dx, dy = end[0] - start[0], end[1] - start[1]
    return start, ((start[0] + end[0]) / 2.0 - dy * 0.18, (start[1] + end[1]) / 2.0 + dx * 0.18), end


def arrow_points(spec: MultileaderSpec) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    route = leader_points(spec)
    target = route[1]
    dx, dy = target[0] - spec.tip[0], target[1] - spec.tip[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        dx, dy, length = 1.0, 0.0, 1.0
    ux, uy = dx / length, dy / length
    size = min(max(spec.height * 0.9, 0.12), max(length * 0.45, 0.12))
    px, py = -uy * size * 0.45, ux * size * 0.45
    base_x, base_y = spec.tip[0] + ux * size, spec.tip[1] + uy * size
    return spec.tip, (base_x + px, base_y + py), (base_x - px, base_y - py)


def metadata_from_entity(entity) -> Optional[Tuple[str, str, MultileaderSpec]]:
    try:
        tags = entity.get_xdata(MULTILEADER_APPID)
    except (AttributeError, ValueError):
        return None
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) != 4 or values[0] != _METADATA_VERSION:
        return None
    try:
        spec = MultileaderSpec.from_payload(json.loads(values[3]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return str(values[1]), str(values[2]), spec


def apply_metadata(entity, identifier: str, role: str, spec: MultileaderSpec) -> None:
    payload = json.dumps(spec.to_payload(), separators=(",", ":"))
    entity.set_xdata(MULTILEADER_APPID, [(1000, _METADATA_VERSION), (1000, identifier), (1000, role), (1000, payload)])


def transform_spec(
    spec: MultileaderSpec,
    transform,
) -> MultileaderSpec:
    landing = transform(spec.landing) if spec.landing is not None else None
    return MultileaderSpec(
        tip=transform(spec.tip),
        landing=landing,
        text_position=transform(spec.text_position),
        text=spec.text,
        height=spec.height,
        line_type=spec.line_type,
        arrowhead=spec.arrowhead,
        attachment=spec.attachment,
        landing_enabled=spec.landing_enabled,
        gap=spec.gap,
        layer=spec.layer,
        identifier=spec.identifier,
    ).normalized()


def with_identifier(spec: MultileaderSpec, identifier: str) -> MultileaderSpec:
    return replace(spec, identifier=identifier).normalized()
