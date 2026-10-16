from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, fields, replace
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ezdxf.render import ARROWS
from ezdxf.tools.text import plain_mtext

from core.fonts import DEFAULT_FONT_ID, font_spec


MULTILEADER_APPID = "GSG_MLEADER"
_METADATA_VERSION = "2"
_LEGACY_METADATA_VERSION = "1"
_XDATA_CHUNK = 240

ARROW_BLOCK_NAMES: Dict[str, str] = {
    "closed": ARROWS.closed_filled,
    "closed_blank": ARROWS.closed_blank,
    "closed_outline": ARROWS.closed,
    "dot": ARROWS.dot,
    "dot_small": ARROWS.dot_small,
    "dot_blank": ARROWS.dot_blank,
    "dot_small_blank": ARROWS.dot_smallblank,
    "open": ARROWS.open,
    "open_30": ARROWS.open_30,
    "right_angle": ARROWS.right_angle,
    "oblique": ARROWS.oblique,
    "architectural_tick": ARROWS.architectural_tick,
    "integral": ARROWS.integral,
    "box": ARROWS.box_filled,
    "box_blank": ARROWS.box,
    "datum_triangle": ARROWS.datum_triangle,
    "datum_triangle_filled": ARROWS.datum_triangle_filled,
    "origin_indicator": ARROWS.origin_indicator,
    "origin_indicator_2": ARROWS.origin_indicator_2,
    "none": ARROWS.none,
}
ARROWHEADS = tuple(ARROW_BLOCK_NAMES)
LINE_TYPES = ("straight", "spline")
ATTACHMENTS = ("auto", "left", "right")
ALIGNMENTS = ("auto", "left", "center", "right")
DIRECTIONS = ("horizontal", "vertical")
HORIZONTAL_CONNECTIONS = (
    "top_of_top_line",
    "middle_of_top_line",
    "middle_of_text",
    "middle_of_bottom_line",
    "bottom_of_bottom_line",
    "bottom_of_bottom_line_underline",
    "bottom_of_top_line_underline",
    "bottom_of_top_line",
    "bottom_of_top_line_underline_all",
)
VERTICAL_CONNECTIONS = ("center", "center_overline")
ANGLE_CONSTRAINTS = (0, 15, 30, 45, 60, 90)
DEFAULT_CONNECTION = "middle_of_top_line"
_LEGACY_CONNECTION = "bottom_of_top_line"

Point = Tuple[float, float]
Color = Optional[Tuple[int, int, int]]


def _point(value: Sequence[float]) -> Point:
    return float(value[0]), float(value[1])


def _color(value: Any) -> Color:
    if value is None:
        return None
    return int(value[0]), int(value[1]), int(value[2])


def _choice(value: Any, options: Sequence[Any], default: Any) -> Any:
    return value if value in options else default


@dataclass(frozen=True)
class MultileaderSpec:
    tip: Point
    landing: Optional[Point]
    text_position: Point
    text: str
    height: float = 0.6
    line_type: str = "straight"
    arrowhead: str = "closed"
    attachment: str = "auto"
    landing_enabled: bool = True
    gap: float = 0.18
    layer: str = "0"
    identifier: str = ""
    landing_length: float = 0.0
    scale: float = 1.0
    style_name: str = ""
    arrow_size: float = 0.0
    arrow_block: str = ""
    leader_color: Color = None
    leader_lineweight: int = -2
    leader_linetype: str = "ByBlock"
    text_color: Color = None
    alignment: str = "auto"
    line_spacing: float = 1.0
    text_frame: bool = False
    background: bool = False
    background_scale: float = 1.5
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font: str = DEFAULT_FONT_ID
    rotation: float = 0.0
    direction: str = "horizontal"
    left_connection: str = DEFAULT_CONNECTION
    right_connection: str = DEFAULT_CONNECTION
    top_connection: str = "center"
    bottom_connection: str = "center"

    @property
    def effective_height(self) -> float:
        return self.height * self.scale

    @property
    def effective_arrow_size(self) -> float:
        if self.arrow_size > 0.0:
            return self.arrow_size * self.scale
        return max(self.effective_height * 0.9, 0.12)

    @property
    def is_vertical(self) -> bool:
        return self.direction == "vertical"

    @property
    def has_landing(self) -> bool:
        return self.landing_enabled and self.landing is not None and not self.is_vertical

    def normalized(self) -> "MultileaderSpec":
        direction = _choice(self.direction, DIRECTIONS, "horizontal")
        landing_length = max(float(self.landing_length), 0.0)
        scale = max(float(self.scale), 0.001)
        rotation = float(self.rotation) % 360.0
        tip = _point(self.tip)
        text_position = _point(self.text_position)
        landing = _point(self.landing) if self.landing is not None else None
        landing_enabled = bool(
            self.landing_enabled and direction == "horizontal" and (landing is not None or landing_length > 0.0)
        )
        attachment = _choice(self.attachment, ATTACHMENTS, "auto")
        if landing_enabled:
            if landing_length > 0.0:
                side = _horizontal_side(attachment, tip, text_position, rotation)
                sign = 1.0 if side == "left" else -1.0
                local = _to_local(text_position, rotation)
                landing = _from_local((local[0] - sign * landing_length * scale, local[1]), rotation)
            elif landing is not None:
                local_landing = _to_local(landing, rotation)
                local_text = _to_local(text_position, rotation)
                text_position = _from_local((local_text[0], local_landing[1]), rotation)
        return MultileaderSpec(
            tip=tip,
            landing=landing,
            text_position=text_position,
            text=str(self.text),
            height=max(float(self.height), 0.01),
            line_type=_choice(self.line_type, LINE_TYPES, "straight"),
            arrowhead=_choice(self.arrowhead, ARROWHEADS, "closed"),
            attachment=attachment,
            landing_enabled=landing_enabled,
            gap=max(float(self.gap), 0.0),
            layer=str(self.layer),
            identifier=self.identifier or uuid.uuid4().hex,
            landing_length=landing_length,
            scale=scale,
            style_name=str(self.style_name),
            arrow_size=max(float(self.arrow_size), 0.0),
            arrow_block=str(self.arrow_block),
            leader_color=_color(self.leader_color),
            leader_lineweight=int(self.leader_lineweight),
            leader_linetype=str(self.leader_linetype) or "ByBlock",
            text_color=_color(self.text_color),
            alignment=_choice(self.alignment, ALIGNMENTS, "auto"),
            line_spacing=min(max(float(self.line_spacing), 0.25), 4.0),
            text_frame=bool(self.text_frame),
            background=bool(self.background),
            background_scale=min(max(float(self.background_scale), 1.0), 5.0),
            bold=bool(self.bold),
            italic=bool(self.italic),
            underline=bool(self.underline),
            font=font_spec(str(self.font)).id,
            rotation=rotation,
            direction=direction,
            left_connection=_choice(self.left_connection, HORIZONTAL_CONNECTIONS, DEFAULT_CONNECTION),
            right_connection=_choice(self.right_connection, HORIZONTAL_CONNECTIONS, DEFAULT_CONNECTION),
            top_connection=_choice(self.top_connection, VERTICAL_CONNECTIONS, "center"),
            bottom_connection=_choice(self.bottom_connection, VERTICAL_CONNECTIONS, "center"),
        )

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "MultileaderSpec":
        known = {field.name for field in fields(cls)}
        values = {key: value for key, value in payload.items() if key in known}
        values["tip"] = tuple(payload["tip"])
        values["text_position"] = tuple(payload["text_position"])
        landing = payload.get("landing")
        values["landing"] = tuple(landing) if landing is not None else None
        values.setdefault("text", "")
        values.setdefault("landing_enabled", landing is not None)
        return cls(**values).normalized()

    @classmethod
    def from_legacy_payload(cls, payload: Dict[str, Any]) -> "MultileaderSpec":
        attachment = payload.get("attachment", "left")
        gap = float(payload.get("gap", 0.18))
        x, y = payload["text_position"]
        sign = -1.0 if attachment == "left" else 1.0
        upgraded = dict(payload)
        upgraded["text_position"] = (x + sign * gap, y)
        upgraded["attachment"] = attachment
        upgraded["left_connection"] = _LEGACY_CONNECTION
        upgraded["right_connection"] = _LEGACY_CONNECTION
        return cls.from_payload(upgraded)


@dataclass(frozen=True)
class MultileaderStyle:
    name: str
    arrowhead: str = "closed"
    line_type: str = "straight"
    height: float = 0.6
    gap: float = 0.18
    landing_length: float = 0.0
    scale: float = 1.0
    annotative: bool = False
    arrow_size: float = 0.0
    arrow_block: str = ""
    leader_color: Color = None
    leader_lineweight: int = -2
    leader_linetype: str = "ByBlock"
    text_color: Color = None
    line_spacing: float = 1.0
    text_frame: bool = False
    background: bool = False
    background_scale: float = 1.5
    bold: bool = False
    italic: bool = False
    underline: bool = False
    font: str = DEFAULT_FONT_ID
    direction: str = "horizontal"
    left_connection: str = DEFAULT_CONNECTION
    right_connection: str = DEFAULT_CONNECTION
    top_connection: str = "center"
    bottom_connection: str = "center"
    landing_enabled: bool = True
    first_angle: int = 0
    second_angle: int = 0

    def normalized(self) -> "MultileaderStyle":
        return MultileaderStyle(
            name=str(self.name).strip(),
            arrowhead=_choice(self.arrowhead, ARROWHEADS, "closed"),
            line_type=_choice(self.line_type, LINE_TYPES, "straight"),
            height=max(float(self.height), 0.01),
            gap=max(float(self.gap), 0.0),
            landing_length=max(float(self.landing_length), 0.0),
            scale=max(float(self.scale), 0.001),
            annotative=bool(self.annotative),
            arrow_size=max(float(self.arrow_size), 0.0),
            arrow_block=str(self.arrow_block),
            leader_color=_color(self.leader_color),
            leader_lineweight=int(self.leader_lineweight),
            leader_linetype=str(self.leader_linetype) or "ByBlock",
            text_color=_color(self.text_color),
            line_spacing=min(max(float(self.line_spacing), 0.25), 4.0),
            text_frame=bool(self.text_frame),
            background=bool(self.background),
            background_scale=min(max(float(self.background_scale), 1.0), 5.0),
            bold=bool(self.bold),
            italic=bool(self.italic),
            underline=bool(self.underline),
            font=font_spec(str(self.font)).id,
            direction=_choice(self.direction, DIRECTIONS, "horizontal"),
            left_connection=_choice(self.left_connection, HORIZONTAL_CONNECTIONS, DEFAULT_CONNECTION),
            right_connection=_choice(self.right_connection, HORIZONTAL_CONNECTIONS, DEFAULT_CONNECTION),
            top_connection=_choice(self.top_connection, VERTICAL_CONNECTIONS, "center"),
            bottom_connection=_choice(self.bottom_connection, VERTICAL_CONNECTIONS, "center"),
            landing_enabled=bool(self.landing_enabled),
            first_angle=int(_choice(int(self.first_angle), ANGLE_CONSTRAINTS, 0)),
            second_angle=int(_choice(int(self.second_angle), ANGLE_CONSTRAINTS, 0)),
        )

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "MultileaderStyle":
        known = {field.name for field in fields(cls)}
        values = {key: value for key, value in payload.items() if key in known}
        values["name"] = str(payload["name"])
        return cls(**values).normalized()


_STYLE_FIELDS = tuple(
    field.name
    for field in fields(MultileaderStyle)
    if field.name not in {"name", "annotative", "first_angle", "second_angle"}
)


def apply_style(spec: MultileaderSpec, style: MultileaderStyle) -> MultileaderSpec:
    style = style.normalized()
    changes = {name: getattr(style, name) for name in _STYLE_FIELDS}
    if not style.landing_enabled:
        changes["landing_enabled"] = False
    elif spec.landing is None and style.landing_length <= 0.0:
        changes["landing_enabled"] = spec.landing_enabled
    return replace(spec, style_name=style.name, **changes).normalized()


def rescale_spec(spec: MultileaderSpec, scale: float) -> MultileaderSpec:
    return replace(spec, scale=scale).normalized()


def _rotate(point: Point, degrees: float) -> Point:
    if not degrees:
        return point
    radians = math.radians(degrees)
    cos_a, sin_a = math.cos(radians), math.sin(radians)
    return point[0] * cos_a - point[1] * sin_a, point[0] * sin_a + point[1] * cos_a


def _to_local(point: Point, rotation: float) -> Point:
    return _rotate(point, -rotation)


def _from_local(point: Point, rotation: float) -> Point:
    return _rotate(point, rotation)


def _horizontal_side(attachment: str, anchor: Point, text_position: Point, rotation: float) -> str:
    if attachment in ("left", "right"):
        return attachment
    return "left" if _to_local(text_position, rotation)[0] >= _to_local(anchor, rotation)[0] else "right"


def connection_side(spec: MultileaderSpec) -> str:
    if spec.is_vertical:
        above = _to_local(spec.text_position, spec.rotation)[1] >= _to_local(spec.tip, spec.rotation)[1]
        return "bottom" if above else "top"
    anchor = spec.landing if spec.has_landing and spec.landing_length <= 0.0 else spec.tip
    return _horizontal_side(spec.attachment, anchor, spec.text_position, spec.rotation)


def text_alignment(spec: MultileaderSpec) -> str:
    if spec.alignment != "auto":
        return spec.alignment
    side = connection_side(spec)
    if side in ("top", "bottom"):
        return "center"
    return side


def text_connection(spec: MultileaderSpec) -> Point:
    return spec.text_position


def dogleg_length(spec: MultileaderSpec) -> float:
    if not spec.has_landing:
        return 0.0
    landing = _to_local(spec.landing, spec.rotation)
    text = _to_local(spec.text_position, spec.rotation)
    return abs(text[0] - landing[0])


def move_text(spec: MultileaderSpec, point: Point) -> MultileaderSpec:
    if not spec.has_landing:
        return replace(spec, text_position=point).normalized()
    length = dogleg_length(spec)
    local = _to_local(point, spec.rotation)
    side = _horizontal_side(spec.attachment, spec.tip, point, spec.rotation)
    sign = 1.0 if side == "left" else -1.0
    landing = _from_local((local[0] - sign * length, local[1]), spec.rotation)
    return replace(spec, text_position=point, landing=landing).normalized()


def leader_points(spec: MultileaderSpec) -> Tuple[Point, ...]:
    end = text_connection(spec)
    if spec.has_landing:
        return spec.tip, spec.landing, end
    return spec.tip, end


def leader_vertices(spec: MultileaderSpec) -> Tuple[Point, ...]:
    route = leader_points(spec)
    if spec.line_type != "spline":
        return (spec.tip,)
    end = route[1]
    dx, dy = end[0] - spec.tip[0], end[1] - spec.tip[1]
    return spec.tip, ((spec.tip[0] + end[0]) / 2.0 - dy * 0.18, (spec.tip[1] + end[1]) / 2.0 + dx * 0.18)


def spline_fit_points(spec: MultileaderSpec) -> Tuple[Point, ...]:
    route = leader_points(spec)
    vertices = leader_vertices(spec)
    return (*vertices, *route[1:])


def arrow_points(spec: MultileaderSpec) -> Tuple[Point, Point, Point]:
    route = leader_points(spec)
    target = route[1]
    dx, dy = target[0] - spec.tip[0], target[1] - spec.tip[1]
    length = math.hypot(dx, dy)
    if length <= 1e-9:
        dx, dy, length = 1.0, 0.0, 1.0
    ux, uy = dx / length, dy / length
    size = min(spec.effective_arrow_size, max(length * 0.45, 0.12))
    px, py = -uy * size * 0.45, ux * size * 0.45
    base_x, base_y = spec.tip[0] + ux * size, spec.tip[1] + uy * size
    return spec.tip, (base_x + px, base_y + py), (base_x - px, base_y - py)


def _escape_mtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\r\n", "\n")
        .replace("\n", "\\P")
    )


def mtext_content(spec: MultileaderSpec) -> str:
    content = _escape_mtext(spec.text)
    if spec.underline:
        content = "\\L" + content + "\\l"
    font = font_spec(spec.font)
    if spec.bold and font.category == "standard" and font.fallback_families:
        flags = f"|b1|i{1 if spec.italic else 0}|c0|p0"
        content = "{\\f" + font.fallback_families[0] + flags + ";" + content + "}"
    return content


def text_from_mtext(content: str) -> str:
    return plain_mtext(content, split=False)


def constrain_angle(origin: Point, point: Point, step: int) -> Point:
    if step <= 0:
        return point
    dx, dy = point[0] - origin[0], point[1] - origin[1]
    length = math.hypot(dx, dy)
    if length <= 1e-12:
        return point
    angle = math.degrees(math.atan2(dy, dx))
    snapped = math.radians(round(angle / step) * step)
    return origin[0] + math.cos(snapped) * length, origin[1] + math.sin(snapped) * length


def _xdata_chunks(value: str) -> List[str]:
    return [value[index : index + _XDATA_CHUNK] for index in range(0, len(value), _XDATA_CHUNK)] or [""]


def metadata_from_entity(entity) -> Optional[Tuple[str, MultileaderSpec]]:
    try:
        tags = entity.get_xdata(MULTILEADER_APPID)
    except (AttributeError, ValueError):
        return None
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) < 3 or values[0] != _METADATA_VERSION:
        return None
    try:
        spec = MultileaderSpec.from_payload(json.loads("".join(values[2:])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return str(values[1]), spec


def legacy_metadata_from_entity(entity) -> Optional[Tuple[str, str, MultileaderSpec]]:
    try:
        tags = entity.get_xdata(MULTILEADER_APPID)
    except (AttributeError, ValueError):
        return None
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) != 4 or values[0] != _LEGACY_METADATA_VERSION:
        return None
    try:
        spec = MultileaderSpec.from_legacy_payload(json.loads(values[3]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return str(values[1]), str(values[2]), spec


def apply_metadata(entity, spec: MultileaderSpec) -> None:
    payload = json.dumps(spec.to_payload(), separators=(",", ":"))
    tags = [(1000, _METADATA_VERSION), (1000, spec.identifier)]
    tags.extend((1000, chunk) for chunk in _xdata_chunks(payload))
    entity.set_xdata(MULTILEADER_APPID, tags)


def style_metadata(style: MultileaderStyle) -> List[Tuple[int, str]]:
    payload = json.dumps(style.to_payload(), separators=(",", ":"))
    return [(1000, _METADATA_VERSION), *((1000, chunk) for chunk in _xdata_chunks(payload))]


def style_from_metadata(tags) -> Optional[MultileaderStyle]:
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) < 2 or values[0] != _METADATA_VERSION:
        return None
    try:
        return MultileaderStyle.from_payload(json.loads("".join(values[1:])))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def spec_from_native(entity) -> Optional[MultileaderSpec]:
    context = getattr(entity, "context", None)
    if context is None or not context.leaders:
        return None
    leader = context.leaders[0]
    if not leader.lines or not leader.lines[0].vertices:
        return None
    tip = leader.lines[0].vertices[0]
    last = leader.last_leader_point
    dogleg = leader.dogleg_vector
    has_dogleg = bool(entity.dxf.get("has_dogleg", 0)) and leader.dogleg_length > 0.0
    connection = last + dogleg * leader.dogleg_length if has_dogleg else last
    mtext = context.mtext
    text = text_from_mtext(mtext.default_content) if mtext is not None else ""
    rotation = math.degrees(mtext.rotation) if mtext is not None else 0.0
    vertical = int(entity.dxf.get("text_attachment_direction", 0)) == 1
    scale = float(entity.dxf.get("scale", 1.0)) or 1.0
    return MultileaderSpec(
        tip=(tip.x, tip.y),
        landing=(last.x, last.y) if has_dogleg else None,
        text_position=(connection.x, connection.y),
        text=text,
        height=float(context.char_height) / scale,
        scale=scale,
        line_type="spline" if int(entity.dxf.get("leader_type", 1)) == 2 else "straight",
        landing_enabled=has_dogleg,
        gap=float(context.landing_gap_size),
        layer=str(entity.dxf.layer),
        arrow_size=float(context.arrow_head_size) / scale,
        rotation=rotation,
        direction="vertical" if vertical else "horizontal",
    ).normalized()


def transform_spec(
    spec: MultileaderSpec,
    transform: Callable[[Point], Point],
    length_factor: float = 1.0,
    rotation_delta: float = 0.0,
) -> MultileaderSpec:
    landing = transform(spec.landing) if spec.landing is not None else None
    return replace(
        spec,
        tip=transform(spec.tip),
        landing=landing,
        text_position=transform(spec.text_position),
        height=spec.height * length_factor,
        gap=spec.gap * length_factor,
        arrow_size=spec.arrow_size * length_factor,
        landing_length=spec.landing_length * length_factor,
        rotation=spec.rotation + rotation_delta,
    ).normalized()


def with_identifier(spec: MultileaderSpec, identifier: str) -> MultileaderSpec:
    return replace(spec, identifier=identifier).normalized()
