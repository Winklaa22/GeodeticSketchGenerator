from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ezdxf import colors as ezdxf_colors
from ezdxf.entities import DXFGraphic
from ezdxf.math import Vec3

from core.exceptions import InvalidPropertyValueError

GROUP_GENERAL = "general"
GROUP_GEOMETRY = "geometry"
GROUP_TEXT = "text"

KIND_LAYER = "layer"
KIND_COLOR = "color"
KIND_LINETYPE = "linetype"
KIND_LINEWEIGHT = "lineweight"
KIND_TRANSPARENCY = "transparency"
KIND_NUMBER = "number"
KIND_ANGLE = "angle"
KIND_TEXT = "text"
KIND_BOOL = "bool"

LINEWEIGHT_BYLAYER = -1
LINEWEIGHT_BYBLOCK = -2
LINEWEIGHT_DEFAULT = -3
LINEWEIGHTS: Tuple[int, ...] = (
    LINEWEIGHT_BYLAYER,
    LINEWEIGHT_BYBLOCK,
    LINEWEIGHT_DEFAULT,
    0, 5, 9, 13, 15, 18, 20, 25, 30, 35, 40, 50, 53, 60, 70, 80, 90, 100, 106, 120, 140, 158, 200, 211,
)

TRANSPARENCY_BYLAYER = -1
TRANSPARENCY_BYBLOCK = -2
TRANSPARENCY_MAX_PERCENT = 90

ACI_BYBLOCK = 0
ACI_BYLAYER = 256

_EQUAL_TOLERANCE = 1e-9


class _Varies:

    def __repr__(self) -> str:
        return "VARIES"


VARIES: Any = _Varies()


@dataclass(frozen=True)
class ColorValue:

    aci: int
    rgb: Optional[Tuple[int, int, int]] = None


BYLAYER_COLOR = ColorValue(ACI_BYLAYER)
BYBLOCK_COLOR = ColorValue(ACI_BYBLOCK)


@lru_cache(maxsize=None)
def nearest_aci(rgb: Tuple[int, int, int]) -> int:
    best_aci, best_distance = 7, None
    for aci in range(1, 256):
        candidate = ezdxf_colors.aci2rgb(aci)
        distance = (
            (candidate.r - rgb[0]) ** 2 + (candidate.g - rgb[1]) ** 2 + (candidate.b - rgb[2]) ** 2
        )
        if best_distance is None or distance < best_distance:
            best_distance, best_aci = distance, aci
    return best_aci


def true_color(rgb: Tuple[int, int, int]) -> ColorValue:
    return ColorValue(nearest_aci(rgb), rgb)


def aci_rgb(aci: int) -> Tuple[int, int, int]:
    rgb = ezdxf_colors.aci2rgb(abs(aci))
    return rgb.r, rgb.g, rgb.b


@dataclass(frozen=True)
class PropertySpec:

    key: str
    group: str
    kind: str
    getter: Callable[[DXFGraphic], Any]
    setter: Optional[Callable[[DXFGraphic, Any], None]] = None


@dataclass(frozen=True)
class PropertyRow:

    key: str
    group: str
    kind: str
    value: Any
    editable: bool


def _get_color(entity: DXFGraphic) -> ColorValue:
    rgb = entity.rgb
    return ColorValue(entity.dxf.color, (rgb[0], rgb[1], rgb[2]) if rgb is not None else None)


def _set_color(entity: DXFGraphic, value: ColorValue) -> None:
    entity.dxf.color = value.aci
    if value.rgb is not None:
        entity.rgb = value.rgb
    else:
        entity.dxf.discard("true_color")


def _get_linetype(entity: DXFGraphic) -> str:
    name = entity.dxf.linetype
    if name.lower() == "bylayer":
        return "ByLayer"
    if name.lower() == "byblock":
        return "ByBlock"
    return name


def _get_transparency(entity: DXFGraphic) -> int:
    if not entity.dxf.hasattr("transparency"):
        return TRANSPARENCY_BYLAYER
    raw = entity.dxf.transparency
    if raw == ezdxf_colors.TRANSPARENCY_BYBLOCK:
        return TRANSPARENCY_BYBLOCK
    return round(ezdxf_colors.transparency2float(raw) * 100)


def _set_transparency(entity: DXFGraphic, value: int) -> None:
    if value == TRANSPARENCY_BYLAYER:
        entity.dxf.discard("transparency")
    elif value == TRANSPARENCY_BYBLOCK:
        entity.dxf.transparency = ezdxf_colors.TRANSPARENCY_BYBLOCK
    else:
        percent = max(0, min(TRANSPARENCY_MAX_PERCENT, int(value)))
        entity.dxf.transparency = ezdxf_colors.float2transparency(percent / 100.0)


def _attr(name: str, default: Any = None) -> Callable[[DXFGraphic], Any]:
    return lambda entity: entity.dxf.get(name, default)


def _set_attr(name: str, convert: Callable[[Any], Any] = float) -> Callable[[DXFGraphic, Any], None]:
    def setter(entity: DXFGraphic, value: Any) -> None:
        entity.dxf.set(name, convert(value))

    return setter


def _coord(name: str, axis: int) -> Callable[[DXFGraphic], float]:
    return lambda entity: float(Vec3(entity.dxf.get(name, (0, 0, 0)))[axis])


def _set_coord(name: str, axis: int) -> Callable[[DXFGraphic, Any], None]:
    def setter(entity: DXFGraphic, value: Any) -> None:
        point = list(Vec3(entity.dxf.get(name, (0, 0, 0))))
        point[axis] = float(value)
        entity.dxf.set(name, Vec3(point))

    return setter


def _normalized_angle(degrees: float) -> float:
    angle = degrees % 360.0
    return 0.0 if math.isclose(angle, 360.0) else angle


def _line_delta(entity: DXFGraphic) -> Vec3:
    return Vec3(entity.dxf.end) - Vec3(entity.dxf.start)


def _line_angle(entity: DXFGraphic) -> float:
    delta = _line_delta(entity)
    return _normalized_angle(math.degrees(math.atan2(delta.y, delta.x)))


def _arc_total_angle(entity: DXFGraphic) -> float:
    total = (entity.dxf.end_angle - entity.dxf.start_angle) % 360.0
    return 360.0 if math.isclose(total, 0.0) else total


def _polyline_vertices(entity: DXFGraphic) -> List[Tuple[Vec3, float]]:
    if entity.dxftype() == "LWPOLYLINE":
        elevation = entity.dxf.get("elevation", 0.0)
        return [(Vec3(x, y, elevation), bulge) for x, y, bulge in entity.get_points("xyb")]
    return [(Vec3(vertex.dxf.location), vertex.dxf.get("bulge", 0.0)) for vertex in entity.vertices]


def _polyline_segments(entity: DXFGraphic, closed: bool) -> List[Tuple[Vec3, Vec3, float]]:
    vertices = _polyline_vertices(entity)
    segments = [(a, b, bulge) for (a, bulge), (b, _next) in zip(vertices, vertices[1:])]
    if closed and len(vertices) > 1:
        segments.append((vertices[-1][0], vertices[0][0], vertices[-1][1]))
    return segments


def _bulge_arc(chord: float, bulge: float) -> Tuple[float, float]:
    theta = 4.0 * math.atan(abs(bulge))
    radius = chord / (2.0 * math.sin(theta / 2.0))
    return theta, radius


def _path_length(entity: DXFGraphic) -> float:
    total = 0.0
    for start, end, bulge in _polyline_segments(entity, _is_closed(entity)):
        chord = start.distance(end)
        if bulge == 0.0 or chord == 0.0:
            total += chord
        else:
            theta, radius = _bulge_arc(chord, bulge)
            total += radius * theta
    return total


def _path_area(entity: DXFGraphic) -> float:
    closed = _is_closed(entity)
    segments = _polyline_segments(entity, closed)
    if not closed and segments:
        segments.append((segments[-1][1], segments[0][0], 0.0))
    signed = 0.0
    for start, end, bulge in segments:
        signed += (start.x * end.y - end.x * start.y) / 2.0
        chord = start.vec2.distance(end.vec2)
        if bulge != 0.0 and chord != 0.0:
            theta, radius = _bulge_arc(chord, bulge)
            signed += math.copysign(radius * radius * (theta - math.sin(theta)) / 2.0, bulge)
    return abs(signed)


def _is_closed(entity: DXFGraphic) -> bool:
    return bool(entity.closed) if entity.dxftype() == "LWPOLYLINE" else bool(entity.is_closed)


def _set_closed(entity: DXFGraphic, value: Any) -> None:
    if entity.dxftype() == "LWPOLYLINE":
        entity.closed = bool(value)
    else:
        entity.close(bool(value))


def _text_is_aligned(entity: DXFGraphic) -> bool:
    return entity.dxf.get("halign", 0) != 0 or entity.dxf.get("valign", 0) != 0


def _text_anchor_name(entity: DXFGraphic) -> str:
    return "align_point" if _text_is_aligned(entity) and entity.dxf.hasattr("align_point") else "insert"


def _get_text_position(axis: int) -> Callable[[DXFGraphic], float]:
    return lambda entity: _coord(_text_anchor_name(entity), axis)(entity)


def _set_text_position(axis: int) -> Callable[[DXFGraphic, Any], None]:
    def setter(entity: DXFGraphic, value: Any) -> None:
        anchor = _text_anchor_name(entity)
        offset = float(value) - _coord(anchor, axis)(entity)
        for name in ("insert", "align_point"):
            if entity.dxf.hasattr(name):
                point = list(Vec3(entity.dxf.get(name)))
                point[axis] += offset
                entity.dxf.set(name, Vec3(point))

    return setter


def _set_mtext_contents(entity: DXFGraphic, value: Any) -> None:
    entity.text = str(value)


def _set_mtext_rotation(entity: DXFGraphic, value: Any) -> None:
    entity.set_rotation(float(value))


def _positive(value: Any) -> float:
    number = float(value)
    if number <= 0.0:
        raise InvalidPropertyValueError(f"Value must be greater than zero, got {number:g}.")
    return number


def _set_positive(name: str) -> Callable[[DXFGraphic, Any], None]:
    return _set_attr(name, _positive)


def _set_diameter(entity: DXFGraphic, value: Any) -> None:
    entity.dxf.radius = _positive(value) / 2.0


def _set_layer(entity: DXFGraphic, value: Any) -> None:
    entity.dxf.layer = str(value)


def _set_linetype(entity: DXFGraphic, value: Any) -> None:
    entity.dxf.linetype = str(value)


def _set_lineweight(entity: DXFGraphic, value: Any) -> None:
    entity.dxf.lineweight = int(value)


GENERAL_SPECS: Tuple[PropertySpec, ...] = (
    PropertySpec("layer", GROUP_GENERAL, KIND_LAYER, _attr("layer", "0"), _set_layer),
    PropertySpec("color", GROUP_GENERAL, KIND_COLOR, _get_color, _set_color),
    PropertySpec("linetype", GROUP_GENERAL, KIND_LINETYPE, _get_linetype, _set_linetype),
    PropertySpec("ltscale", GROUP_GENERAL, KIND_NUMBER, _attr("ltscale", 1.0), _set_positive("ltscale")),
    PropertySpec("lineweight", GROUP_GENERAL, KIND_LINEWEIGHT, _attr("lineweight", LINEWEIGHT_BYLAYER), _set_lineweight),
    PropertySpec("transparency", GROUP_GENERAL, KIND_TRANSPARENCY, _get_transparency, _set_transparency),
)


def _point_specs(prefix: str, attribute: str, group: str = GROUP_GEOMETRY) -> Tuple[PropertySpec, ...]:
    return (
        PropertySpec(f"{prefix}_x", group, KIND_NUMBER, _coord(attribute, 0), _set_coord(attribute, 0)),
        PropertySpec(f"{prefix}_y", group, KIND_NUMBER, _coord(attribute, 1), _set_coord(attribute, 1)),
    )


_LINE_SPECS = (
    *_point_specs("start", "start"),
    *_point_specs("end", "end"),
    PropertySpec("delta_x", GROUP_GEOMETRY, KIND_NUMBER, lambda e: _line_delta(e).x),
    PropertySpec("delta_y", GROUP_GEOMETRY, KIND_NUMBER, lambda e: _line_delta(e).y),
    PropertySpec("length", GROUP_GEOMETRY, KIND_NUMBER, lambda e: _line_delta(e).magnitude),
    PropertySpec("angle", GROUP_GEOMETRY, KIND_ANGLE, _line_angle),
)

_CIRCLE_SPECS = (
    *_point_specs("center", "center"),
    PropertySpec("radius", GROUP_GEOMETRY, KIND_NUMBER, _attr("radius"), _set_positive("radius")),
    PropertySpec("diameter", GROUP_GEOMETRY, KIND_NUMBER, lambda e: e.dxf.radius * 2.0, _set_diameter),
    PropertySpec("circumference", GROUP_GEOMETRY, KIND_NUMBER, lambda e: 2.0 * math.pi * e.dxf.radius),
    PropertySpec("area", GROUP_GEOMETRY, KIND_NUMBER, lambda e: math.pi * e.dxf.radius ** 2),
)

_ARC_SPECS = (
    *_point_specs("center", "center"),
    PropertySpec("radius", GROUP_GEOMETRY, KIND_NUMBER, _attr("radius"), _set_positive("radius")),
    PropertySpec("start_angle", GROUP_GEOMETRY, KIND_ANGLE, lambda e: _normalized_angle(e.dxf.start_angle), _set_attr("start_angle")),
    PropertySpec("end_angle", GROUP_GEOMETRY, KIND_ANGLE, lambda e: _normalized_angle(e.dxf.end_angle), _set_attr("end_angle")),
    PropertySpec("total_angle", GROUP_GEOMETRY, KIND_ANGLE, _arc_total_angle),
    PropertySpec("arc_length", GROUP_GEOMETRY, KIND_NUMBER, lambda e: e.dxf.radius * math.radians(_arc_total_angle(e))),
)

_POLYLINE_SHAPE_SPECS = (
    PropertySpec("closed", GROUP_GEOMETRY, KIND_BOOL, _is_closed, _set_closed),
    PropertySpec("length", GROUP_GEOMETRY, KIND_NUMBER, _path_length),
    PropertySpec("area", GROUP_GEOMETRY, KIND_NUMBER, _path_area),
)

_LWPOLYLINE_SPECS = (
    PropertySpec("constant_width", GROUP_GEOMETRY, KIND_NUMBER, _attr("const_width", 0.0), _set_attr("const_width")),
    *_POLYLINE_SHAPE_SPECS,
)

_TEXT_SPECS = (
    PropertySpec("contents", GROUP_TEXT, KIND_TEXT, _attr("text", ""), _set_attr("text", str)),
    PropertySpec("height", GROUP_TEXT, KIND_NUMBER, _attr("height", 1.0), _set_positive("height")),
    PropertySpec("rotation", GROUP_TEXT, KIND_ANGLE, lambda e: _normalized_angle(e.dxf.get("rotation", 0.0)), _set_attr("rotation")),
    PropertySpec("position_x", GROUP_GEOMETRY, KIND_NUMBER, _get_text_position(0), _set_text_position(0)),
    PropertySpec("position_y", GROUP_GEOMETRY, KIND_NUMBER, _get_text_position(1), _set_text_position(1)),
)

_MTEXT_SPECS = (
    PropertySpec("contents", GROUP_TEXT, KIND_TEXT, lambda e: e.text, _set_mtext_contents),
    PropertySpec("height", GROUP_TEXT, KIND_NUMBER, _attr("char_height", 1.0), _set_positive("char_height")),
    PropertySpec("rotation", GROUP_TEXT, KIND_ANGLE, lambda e: _normalized_angle(e.get_rotation()), _set_mtext_rotation),
    PropertySpec("width", GROUP_TEXT, KIND_NUMBER, _attr("width", 0.0), _set_attr("width")),
    *_point_specs("position", "insert"),
)

_INSERT_SPECS = (
    PropertySpec("name", GROUP_GEOMETRY, KIND_TEXT, _attr("name", "")),
    *_point_specs("position", "insert"),
    PropertySpec("rotation", GROUP_GEOMETRY, KIND_ANGLE, lambda e: _normalized_angle(e.dxf.get("rotation", 0.0)), _set_attr("rotation")),
    PropertySpec("scale_x", GROUP_GEOMETRY, KIND_NUMBER, _attr("xscale", 1.0), _set_attr("xscale")),
    PropertySpec("scale_y", GROUP_GEOMETRY, KIND_NUMBER, _attr("yscale", 1.0), _set_attr("yscale")),
)

_POINT_SPECS = _point_specs("position", "location")

_TYPE_SPECS: Dict[str, Tuple[PropertySpec, ...]] = {
    "LINE": _LINE_SPECS,
    "CIRCLE": _CIRCLE_SPECS,
    "ARC": _ARC_SPECS,
    "LWPOLYLINE": _LWPOLYLINE_SPECS,
    "TEXT": _TEXT_SPECS,
    "MTEXT": _MTEXT_SPECS,
    "INSERT": _INSERT_SPECS,
    "POINT": _POINT_SPECS,
}


def specs_for(entity: DXFGraphic) -> Tuple[PropertySpec, ...]:
    dxftype = entity.dxftype()
    if dxftype == "POLYLINE":
        own = _POLYLINE_SHAPE_SPECS if entity.is_2d_polyline or entity.is_3d_polyline else ()
    else:
        own = _TYPE_SPECS.get(dxftype, ())
    return GENERAL_SPECS + own


def spec_for(entity: DXFGraphic, key: str) -> PropertySpec:
    for spec in specs_for(entity):
        if spec.key == key:
            return spec
    raise KeyError(f"{entity.dxftype()} has no property {key!r}")


def selection_types(entities: Sequence[DXFGraphic]) -> List[Tuple[str, int]]:
    counts: Dict[str, int] = {}
    for entity in entities:
        counts[entity.dxftype()] = counts.get(entity.dxftype(), 0) + 1
    return list(counts.items())


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=_EQUAL_TOLERANCE, abs_tol=_EQUAL_TOLERANCE)
    return a == b


def _common_value(specs: Sequence[PropertySpec], entities: Sequence[DXFGraphic]) -> Any:
    first = specs[0].getter(entities[0])
    for spec, entity in zip(specs[1:], entities[1:]):
        if not _same(first, spec.getter(entity)):
            return VARIES
    return first


def describe(entities: Sequence[DXFGraphic]) -> List[PropertyRow]:
    if not entities:
        return []
    per_entity = [{spec.key: spec for spec in specs_for(entity)} for entity in entities]
    shared = [spec for spec in specs_for(entities[0]) if all(spec.key in specs for specs in per_entity[1:])]
    rows: List[PropertyRow] = []
    for spec in shared:
        specs = [specs[spec.key] for specs in per_entity]
        rows.append(
            PropertyRow(
                key=spec.key,
                group=spec.group,
                kind=spec.kind,
                value=_common_value(specs, entities),
                editable=all(item.setter is not None for item in specs),
            )
        )
    return rows
