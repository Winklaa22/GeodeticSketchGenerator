from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, replace
from typing import Any, Dict, Optional, Tuple

from ezdxf.math import Matrix44

DETAIL_APPID = "GSG_DETAIL"
_METADATA_VERSION = "1"

MIN_SCALE = 0.05
MAX_SCALE = 500.0
MIN_SIZE = 1e-6


@dataclass(frozen=True)
class DetailViewSpec:
    center: Tuple[float, float]
    width: float
    height: float
    source: Tuple[float, float]
    scale: float = 4.0
    rotation: float = 0.0
    layer: str = "0"
    identifier: str = ""

    def normalized(self) -> "DetailViewSpec":
        return DetailViewSpec(
            center=(float(self.center[0]), float(self.center[1])),
            width=max(abs(float(self.width)), MIN_SIZE),
            height=max(abs(float(self.height)), MIN_SIZE),
            source=(float(self.source[0]), float(self.source[1])),
            scale=min(max(float(self.scale), MIN_SCALE), MAX_SCALE),
            rotation=float(self.rotation) % 360.0,
            layer=str(self.layer),
            identifier=self.identifier or uuid.uuid4().hex,
        )

    def to_payload(self) -> Dict[str, Any]:
        return asdict(self.normalized())

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "DetailViewSpec":
        return cls(
            center=tuple(payload["center"]),
            width=float(payload["width"]),
            height=float(payload["height"]),
            source=tuple(payload["source"]),
            scale=float(payload.get("scale", 4.0)),
            rotation=float(payload.get("rotation", 0.0)),
            layer=str(payload.get("layer", "0")),
            identifier=str(payload.get("identifier", "")),
        ).normalized()


def from_squares(
    source_center: Tuple[float, float],
    source_size: float,
    frame_center: Tuple[float, float],
    frame_size: float,
    layer: str = "0",
) -> DetailViewSpec:
    source_side = max(abs(float(source_size)), MIN_SIZE)
    frame_side = max(abs(float(frame_size)), MIN_SIZE)
    return DetailViewSpec(
        center=(float(frame_center[0]), float(frame_center[1])),
        width=frame_side,
        height=frame_side,
        source=(float(source_center[0]), float(source_center[1])),
        scale=frame_side / source_side,
        layer=layer,
    ).normalized()


def to_local(spec: DetailViewSpec, point: Tuple[float, float]) -> Tuple[float, float]:
    """World point -> offset from the frame centre with the frame's rotation undone."""
    angle = math.radians(-spec.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    dx, dy = point[0] - spec.center[0], point[1] - spec.center[1]
    return dx * cos_a - dy * sin_a, dx * sin_a + dy * cos_a


def to_world(spec: DetailViewSpec, local: Tuple[float, float]) -> Tuple[float, float]:
    """Inverse of :func:`to_local`."""
    angle = math.radians(spec.rotation)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (
        spec.center[0] + local[0] * cos_a - local[1] * sin_a,
        spec.center[1] + local[0] * sin_a + local[1] * cos_a,
    )


def corner_points(spec: DetailViewSpec) -> Tuple[Tuple[float, float], ...]:
    half_w, half_h = spec.width / 2.0, spec.height / 2.0
    return tuple(
        to_world(spec, local)
        for local in (
            (-half_w, -half_h),
            (half_w, -half_h),
            (half_w, half_h),
            (-half_w, half_h),
        )
    )


def handle_points(spec: DetailViewSpec) -> Tuple[Tuple[float, float], ...]:
    """The eight grips, counter-clockwise from the bottom-left corner.

    Even indices are corners, odd indices are edge midpoints, and the grip opposite
    index ``i`` is always ``(i + 4) % 8``. They serve as both the resize handles and the
    points an arrow can be drawn from.
    """
    half_w, half_h = spec.width / 2.0, spec.height / 2.0
    return tuple(
        to_world(spec, local)
        for local in (
            (-half_w, -half_h),
            (0.0, -half_h),
            (half_w, -half_h),
            (half_w, 0.0),
            (half_w, half_h),
            (0.0, half_h),
            (-half_w, half_h),
            (-half_w, 0.0),
        )
    )


def bounds(spec: DetailViewSpec) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    half_w, half_h = spec.width / 2.0, spec.height / 2.0
    cx, cy = spec.center
    return (cx - half_w, cy - half_h), (cx + half_w, cy + half_h)


def source_bounds(spec: DetailViewSpec) -> Tuple[Tuple[float, float], Tuple[float, float]]:
    half_w = spec.width / (2.0 * spec.scale)
    half_h = spec.height / (2.0 * spec.scale)
    sx, sy = spec.source
    return (sx - half_w, sy - half_h), (sx + half_w, sy + half_h)


def detail_matrix(spec: DetailViewSpec) -> Matrix44:
    spec = spec.normalized()
    return Matrix44.chain(
        Matrix44.translate(-spec.source[0], -spec.source[1], 0.0),
        Matrix44.scale(spec.scale, spec.scale, 1.0),
        Matrix44.translate(spec.center[0], spec.center[1], 0.0),
    )


def rotation_matrix(spec: DetailViewSpec) -> Matrix44:
    """Spins the already magnified and cropped content about the frame centre."""
    return Matrix44.chain(
        Matrix44.translate(-spec.center[0], -spec.center[1], 0.0),
        Matrix44.z_rotate(math.radians(spec.rotation)),
        Matrix44.translate(spec.center[0], spec.center[1], 0.0),
    )


def contains_point(spec: DetailViewSpec, point: Tuple[float, float]) -> bool:
    local_x, local_y = to_local(spec, point)
    return abs(local_x) <= spec.width / 2.0 and abs(local_y) <= spec.height / 2.0


def with_scale(spec: DetailViewSpec, scale: float, anchor: Optional[Tuple[float, float]] = None) -> DetailViewSpec:
    current = spec.normalized()
    target = min(max(float(scale), MIN_SCALE), MAX_SCALE)
    if anchor is None or target == current.scale:
        return replace(current, scale=target).normalized()
    source = source_at(current, anchor)
    moved = replace(current, scale=target).normalized()
    keep = source_at(moved, anchor)
    return replace(
        moved, source=(moved.source[0] + source[0] - keep[0], moved.source[1] + source[1] - keep[1])
    ).normalized()


def source_at(spec: DetailViewSpec, point: Tuple[float, float]) -> Tuple[float, float]:
    local_x, local_y = to_local(spec, point)
    return spec.source[0] + local_x / spec.scale, spec.source[1] + local_y / spec.scale


def panned(spec: DetailViewSpec, dx: float, dy: float) -> DetailViewSpec:
    current = spec.normalized()
    # The drag is a world-space delta; the source window lives in the frame's own
    # unrotated space, so undo the rotation before dividing by the magnification.
    local_x, local_y = to_local(current, (current.center[0] + dx, current.center[1] + dy))
    return replace(
        current,
        source=(current.source[0] - local_x / current.scale, current.source[1] - local_y / current.scale),
    ).normalized()


def rotated(spec: DetailViewSpec, degrees: float) -> DetailViewSpec:
    return replace(spec.normalized(), rotation=spec.rotation + float(degrees)).normalized()


def _with_pinned_content(spec: DetailViewSpec, local_center_delta: Tuple[float, float]) -> Tuple[float, float]:
    """The source that keeps the drawing still while the frame centre slides."""
    return (
        spec.source[0] + local_center_delta[0] / spec.scale,
        spec.source[1] + local_center_delta[1] / spec.scale,
    )


def resize_to_handle(spec: DetailViewSpec, index: int, point: Tuple[float, float]) -> DetailViewSpec:
    """Drag one of :func:`handle_points` to ``point``, keeping the opposite grip still.

    A corner scales the frame and its magnification together, so the frame shows exactly
    the same drawing, only bigger. An edge resizes the frame alone at an unchanged
    magnification, so the frame reveals or hides part of the drawing while everything
    already visible stays put.
    """
    current = spec.normalized()
    half_w, half_h = current.width / 2.0, current.height / 2.0
    local_x, local_y = to_local(current, point)
    sign_x = (1.0 if index in (2, 3, 4) else -1.0 if index in (0, 6, 7) else 0.0)
    sign_y = (1.0 if index in (4, 5, 6) else -1.0 if index in (0, 1, 2) else 0.0)

    if sign_x and sign_y:
        anchor = (-sign_x * half_w, -sign_y * half_h)
        factor_x = (local_x - anchor[0]) / (2.0 * sign_x * half_w)
        factor_y = (local_y - anchor[1]) / (2.0 * sign_y * half_h)
        factor = max(factor_x, factor_y, MIN_SIZE)
        moved = (anchor[0] * (1.0 - factor), anchor[1] * (1.0 - factor))
        return replace(
            current,
            center=to_world(current, moved),
            width=current.width * factor,
            height=current.height * factor,
            scale=current.scale * factor,
        ).normalized()

    if sign_x:
        opposite = -sign_x * half_w
        width = max(abs(local_x - opposite), MIN_SIZE)
        local_center = ((local_x + opposite) / 2.0, 0.0)
        return replace(
            current,
            center=to_world(current, local_center),
            width=width,
            source=_with_pinned_content(current, local_center),
        ).normalized()

    opposite = -sign_y * half_h
    height = max(abs(local_y - opposite), MIN_SIZE)
    local_center = (0.0, (local_y + opposite) / 2.0)
    return replace(
        current,
        center=to_world(current, local_center),
        height=height,
        source=_with_pinned_content(current, local_center),
    ).normalized()


def transform_spec(
    spec: DetailViewSpec, transform, length_factor: float = 1.0, rotation_delta: float = 0.0
) -> DetailViewSpec:
    """Move, rotate or scale the frame without changing what it shows.

    ``source`` is deliberately left alone and ``scale`` follows ``length_factor``, so the
    magnified window keeps the same part of the drawing at the same size relative to the
    frame however the frame itself is transformed.
    """
    current = spec.normalized()
    return DetailViewSpec(
        center=transform(current.center),
        width=current.width * length_factor,
        height=current.height * length_factor,
        source=current.source,
        scale=current.scale * length_factor,
        rotation=current.rotation + rotation_delta,
        layer=current.layer,
        identifier=current.identifier,
    ).normalized()


def with_identifier(spec: DetailViewSpec, identifier: str) -> DetailViewSpec:
    return replace(spec, identifier=identifier).normalized()


def metadata_from_entity(entity) -> Optional[DetailViewSpec]:
    try:
        tags = entity.get_xdata(DETAIL_APPID)
    except (AttributeError, ValueError):
        return None
    values = [tag.value for tag in tags if tag.code == 1000]
    if len(values) != 2 or values[0] != _METADATA_VERSION:
        return None
    try:
        return DetailViewSpec.from_payload(json.loads(values[1]))
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def apply_metadata(entity, spec: DetailViewSpec) -> None:
    payload = json.dumps(spec.to_payload(), separators=(",", ":"))
    entity.set_xdata(DETAIL_APPID, [(1000, _METADATA_VERSION), (1000, payload)])
