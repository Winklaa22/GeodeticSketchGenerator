
from __future__ import annotations

import io
import math
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import bbox as ezdxf_bbox, colors as ezdxf_colors, recover
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from ezdxf.math import Matrix44
from ezdxf.sections.tables import LayerTable

from core.multileader import (
    MULTILEADER_APPID,
    MultileaderSpec,
    apply_metadata,
    arrow_points,
    leader_points,
    metadata_from_entity,
    spline_fit_points,
    transform_spec,
    with_identifier,
)

_TEXT_ALIGNMENTS = {
    ("left", "bottom"): TextEntityAlignment.BOTTOM_LEFT,
    ("center", "bottom"): TextEntityAlignment.BOTTOM_CENTER,
    ("right", "bottom"): TextEntityAlignment.BOTTOM_RIGHT,
    ("left", "middle"): TextEntityAlignment.MIDDLE_LEFT,
    ("center", "middle"): TextEntityAlignment.MIDDLE_CENTER,
    ("right", "middle"): TextEntityAlignment.MIDDLE_RIGHT,
    ("left", "top"): TextEntityAlignment.TOP_LEFT,
    ("center", "top"): TextEntityAlignment.TOP_CENTER,
    ("right", "top"): TextEntityAlignment.TOP_RIGHT,
}

DEFAULT_LAYER_NAME = "0"
# DXF layers with no explicit lineweight resolve to AutoCAD's own default (0.25mm), which
# renders noticeably heavier than intended once plotted at true scale (min_lineweight_mm in
# core/plot.py defaults to 0.13). New layers this app creates get that same 0.13mm instead,
# so a fresh project's own lines print as fine as the app already assumes elsewhere. Layers
# read in from an imported/loaded DXF keep whatever lineweight that file already defines.
DEFAULT_LAYER_LINEWEIGHT = 13


@lru_cache(maxsize=None)
def _nearest_aci(rgb: Tuple[int, int, int]) -> int:
    best_aci, best_distance = 7, None
    for aci in range(1, 256):
        candidate = ezdxf_colors.aci2rgb(aci)
        distance = (
            (candidate.r - rgb[0]) ** 2 + (candidate.g - rgb[1]) ** 2 + (candidate.b - rgb[2]) ** 2
        )
        if best_distance is None or distance < best_distance:
            best_distance, best_aci = distance, aci
    return best_aci


@dataclass(frozen=True)
class LayerInfo:

    name: str
    rgb: Tuple[int, int, int]
    visible: bool
    is_active: bool
    entity_count: int


class DXFDocument:

    def __init__(self, drawing: Drawing) -> None:
        self._drawing = drawing

    @classmethod
    def new(cls) -> "DXFDocument":
        drawing = ezdxf.new()
        # Layer "0" always pre-exists, so ensure_layer()/add_layer() never touch it - set its
        # lineweight explicitly here for the same reason they set it on every other new layer.
        drawing.layers.get(DEFAULT_LAYER_NAME).dxf.lineweight = DEFAULT_LAYER_LINEWEIGHT
        return cls(drawing)

    @classmethod
    def load(cls, file_path: str) -> "DXFDocument":
        try:
            drawing = ezdxf.readfile(file_path)
        except ezdxf.DXFStructureError:
            drawing, _auditor = recover.readfile(file_path)
        doc = cls(drawing)
        doc._ensure_all_referenced_layers()
        return doc

    @classmethod
    def from_text(cls, content: str) -> "DXFDocument":
        try:
            drawing = ezdxf.read(io.StringIO(content))
        except ezdxf.DXFStructureError:
            drawing, _auditor = recover.read(io.BytesIO(content.encode("utf-8", errors="surrogateescape")))
        doc = cls(drawing)
        doc._ensure_all_referenced_layers()
        return doc

    def _ensure_all_referenced_layers(self) -> None:
        for entity in self.modelspace:
            self.ensure_layer(entity.dxf.layer)

    def save(self, file_path: str) -> None:
        self._drawing.saveas(file_path)

    def to_text(self) -> str:
        stream = io.StringIO()
        self._drawing.write(stream)
        return stream.getvalue()

    @property
    def drawing(self) -> Drawing:
        return self._drawing

    @property
    def modelspace(self) -> Modelspace:
        return self._drawing.modelspace()

    @property
    def layers(self) -> LayerTable:
        return self._drawing.layers

    def entity_count(self) -> int:
        return len(self.modelspace)

    def layer_count(self) -> int:
        return len(self.layers)

    def get_entity(self, handle: str) -> Optional[DXFGraphic]:
        return self._drawing.entitydb.get(handle)

    def ensure_layer(self, name: str) -> None:
        if name not in self.layers:
            self.layers.add(name, lineweight=DEFAULT_LAYER_LINEWEIGHT)

    def add_point(self, location: Sequence[float], layer: str = "0") -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_point(location, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_line(self, start: Sequence[float], end: Sequence[float], layer: str = "0") -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_line(start, end, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_circle(self, center: Sequence[float], radius: float, layer: str = "0") -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_circle(center, radius, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_text(
        self,
        text: str,
        insert: Sequence[float],
        height: float,
        layer: str = "0",
        rotation: float = 0.0,
        halign: str = "left",
        valign: str = "bottom",
    ) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_text(
            text, height=height, rotation=rotation, dxfattribs={"layer": layer, "insert": insert}
        )
        alignment = _TEXT_ALIGNMENTS.get((halign, valign))
        if alignment is not None and alignment is not TextEntityAlignment.BOTTOM_LEFT:
            entity.set_placement(insert, align=alignment)
        return entity.dxf.handle

    def add_lwpolyline(self, points: Iterable[Sequence[float]], layer: str = "0", closed: bool = False) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_lwpolyline(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_polyline3d(self, points: Iterable[Sequence[float]], layer: str = "0", closed: bool = False) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_polyline3d(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_spline(self, points: Iterable[Sequence[float]], layer: str = "0") -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_spline(fit_points=points, degree=2, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_solid(self, points: Iterable[Sequence[float]], layer: str = "0") -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_solid(points, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_multileader(self, spec: MultileaderSpec) -> Tuple[List[str], str]:
        spec = spec.normalized()
        self.ensure_layer(spec.layer)
        if MULTILEADER_APPID not in self._drawing.appids:
            self._drawing.appids.add(MULTILEADER_APPID)
        handles: List[str] = []
        route = leader_points(spec)
        if spec.line_type == "spline":
            route_handle = self.add_spline(spline_fit_points(spec), spec.layer)
        elif len(route) > 2:
            route_handle = self.add_lwpolyline(route, spec.layer)
        else:
            route_handle = self.add_line(route[0], route[-1], spec.layer)
        handles.append(route_handle)
        tip, left, right = arrow_points(spec)
        if spec.arrowhead == "closed":
            handles.append(self.add_solid((tip, left, right, right), spec.layer))
        elif spec.arrowhead == "open":
            handles.append(self.add_line(tip, left, spec.layer))
            handles.append(self.add_line(tip, right, spec.layer))
        else:
            radius = max(spec.height * 0.28, 0.04)
            handles.append(self.add_circle(tip, radius, spec.layer))
        text_handle = self.add_text(
            spec.text,
            spec.text_position,
            spec.height,
            spec.layer,
            halign=spec.attachment,
        )
        handles.append(text_handle)
        for handle in handles:
            entity = self._require_entity(handle)
            role = "text" if handle == text_handle else "arrow" if handle != route_handle else "leader"
            apply_metadata(entity, spec.identifier, role, spec)
        return handles, text_handle

    def multileader_metadata(self, handle: str):
        entity = self.get_entity(handle)
        return metadata_from_entity(entity) if entity is not None else None

    def multileader_handles(self, handle: str) -> List[str]:
        metadata = self.multileader_metadata(handle)
        if metadata is None:
            return [handle]
        identifier, _role, _spec = metadata
        return [
            entity.dxf.handle
            for entity in self.modelspace
            if (entity_metadata := metadata_from_entity(entity)) is not None and entity_metadata[0] == identifier
        ]

    def expand_annotation_handles(self, handles: Iterable[str]) -> List[str]:
        expanded: List[str] = []
        for handle in handles:
            for related in self.multileader_handles(handle):
                if related not in expanded:
                    expanded.append(related)
        return expanded

    def multileader_text_handle(self, handles: Iterable[str]) -> Optional[str]:
        identifiers = set()
        for handle in handles:
            metadata = self.multileader_metadata(handle)
            if metadata is None:
                return None
            identifiers.add(metadata[0])
        if len(identifiers) != 1:
            return None
        identifier = identifiers.pop()
        for entity in self.modelspace:
            metadata = metadata_from_entity(entity)
            if metadata is not None and metadata[0] == identifier and metadata[1] == "text":
                return entity.dxf.handle
        return None

    def multileader_grips(self, handle: str) -> List[Tuple[float, float]]:
        metadata = self.multileader_metadata(handle)
        if metadata is None:
            return []
        _identifier, _role, spec = metadata
        grips = [spec.tip]
        if spec.landing_enabled and spec.landing is not None:
            grips.append(spec.landing)
        grips.append(spec.text_position)
        return grips

    def separate_multileader_groups(self, handles: Iterable[str], dx: float = 0.0, dy: float = 0.0) -> None:
        handle_set = set(handles)
        identifiers = set()
        for handle in handles:
            metadata = self.multileader_metadata(handle)
            if metadata is not None:
                identifiers.add(metadata[0])
        for identifier in identifiers:
            matching = [
                entity
                for entity in self.modelspace
                if entity.dxf.handle in handle_set
                and (metadata := metadata_from_entity(entity)) is not None
                and metadata[0] == identifier
            ]
            if not matching:
                continue
            _matched_identifier, _role, spec = metadata_from_entity(matching[0])
            new_identifier = uuid.uuid4().hex
            moved = transform_spec(spec, lambda point: (point[0] + dx, point[1] + dy)) if dx or dy else spec
            separated = with_identifier(moved, new_identifier)
            for entity in matching:
                _entity_identifier, role, _entity_spec = metadata_from_entity(entity)
                apply_metadata(entity, new_identifier, role, separated)

    def _transform_multileader_metadata(self, handles: Iterable[str], transform) -> None:
        identifiers = set()
        for handle in handles:
            metadata = self.multileader_metadata(handle)
            if metadata is not None:
                identifiers.add(metadata[0])
        for identifier in identifiers:
            matching = [
                entity
                for entity in self.modelspace
                if (metadata := metadata_from_entity(entity)) is not None and metadata[0] == identifier
            ]
            if not matching:
                continue
            _matched_identifier, _role, spec = metadata_from_entity(matching[0])
            transformed = transform_spec(spec, transform)
            for entity in matching:
                _entity_identifier, role, _entity_spec = metadata_from_entity(entity)
                apply_metadata(entity, identifier, role, transformed)

    def translate_entities(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            self.translate_entity(handle, dx, dy, dz)
        self._transform_multileader_metadata(resolved, lambda point: (point[0] + dx, point[1] + dy))
        return resolved

    def rotate_entities(self, handles: Iterable[str], angle: float, center: Sequence[float]) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            self.rotate_entity(handle, angle, center)
        radians = math.radians(angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        cx, cy = center[0], center[1]
        self._transform_multileader_metadata(
            resolved,
            lambda point: (
                cx + (point[0] - cx) * cos_a - (point[1] - cy) * sin_a,
                cy + (point[0] - cx) * sin_a + (point[1] - cy) * cos_a,
            ),
        )
        return resolved

    def scale_entities(self, handles: Iterable[str], factor: float, center: Sequence[float]) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            self.scale_entity(handle, factor, center)
        cx, cy = center[0], center[1]
        self._transform_multileader_metadata(
            resolved,
            lambda point: (cx + (point[0] - cx) * factor, cy + (point[1] - cy) * factor),
        )
        return resolved

    def _require_entity(self, handle: str) -> DXFGraphic:
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        return entity

    def unlink_entity(self, handle: str) -> Optional[DXFGraphic]:
        entity = self.get_entity(handle)
        if entity is None or entity.get_layout() is None:
            return None
        self.modelspace.unlink_entity(entity)
        return entity

    def restore_entity(self, entity: DXFGraphic) -> None:
        self.modelspace.add_entity(entity)

    def relink_entity(self, handle: str) -> None:
        entity = self.get_entity(handle)
        if entity is not None and entity.get_layout() is None:
            self.modelspace.add_entity(entity)

    def translate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> None:
        self._require_entity(handle).translate(dx, dy, dz)

    def duplicate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> str:
        copy = self._require_entity(handle).copy()
        copy.translate(dx, dy, dz)
        self.modelspace.add_entity(copy)
        return copy.dxf.handle

    def rotate_entity(self, handle: str, angle: float, center: Sequence[float]) -> None:
        cx, cy = center[0], center[1]
        matrix = Matrix44.chain(
            Matrix44.translate(-cx, -cy, 0),
            Matrix44.z_rotate(math.radians(angle)),
            Matrix44.translate(cx, cy, 0),
        )
        self._require_entity(handle).transform(matrix)

    def scale_entity(self, handle: str, factor: float, center: Sequence[float]) -> None:
        cx, cy = center[0], center[1]
        matrix = Matrix44.chain(
            Matrix44.translate(-cx, -cy, 0),
            Matrix44.scale(factor, factor, 1.0),
            Matrix44.translate(cx, cy, 0),
        )
        self._require_entity(handle).transform(matrix)

    def entity_center(self, handle: str) -> Tuple[float, float]:
        box = ezdxf_bbox.extents([self._require_entity(handle)])
        if not box.has_data:
            return 0.0, 0.0
        return box.center.x, box.center.y

    def get_text_content(self, handle: str) -> str:
        return self._require_entity(handle).dxf.text

    def set_text_content(self, handle: str, text: str) -> None:
        self._require_entity(handle).dxf.text = text

    def get_text_height(self, handle: str) -> float:
        return self._require_entity(handle).dxf.height

    def set_text_height(self, handle: str, height: float) -> None:
        self._require_entity(handle).dxf.height = height

    def get_text_rotation(self, handle: str) -> float:
        return self._require_entity(handle).dxf.rotation

    def set_text_rotation(self, handle: str, rotation: float) -> None:
        self._require_entity(handle).dxf.rotation = rotation

    def get_entity_color(self, handle: str) -> Tuple[int, int, int]:
        entity = self._require_entity(handle)
        # A true color (group code 420) overrides BYLAYER/ACI regardless of what dxf.color
        # says - an entity can carry both color=256 (BYLAYER) and an explicit true color at
        # once, and ezdxf's own renderer always prefers the true color in that case.
        rgb = entity.rgb
        if rgb is not None:
            return (rgb.r, rgb.g, rgb.b)
        if entity.dxf.color in (0, 256):
            return self.get_layer_color(entity.dxf.layer)
        try:
            aci_rgb = ezdxf_colors.aci2rgb(abs(entity.dxf.color))
        except IndexError:
            return (255, 255, 255)
        return (aci_rgb.r, aci_rgb.g, aci_rgb.b)

    def set_entity_color(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self._apply_color(self._require_entity(handle), rgb)

    def layer_entity_handles(self, name: str) -> List[str]:
        return [entity.dxf.handle for entity in self.modelspace if entity.dxf.layer == name]

    def entity_color_override(self, handle: str) -> Tuple[int, Optional[Tuple[int, int, int]]]:
        entity = self._require_entity(handle)
        rgb = entity.rgb
        return entity.dxf.color, (rgb.r, rgb.g, rgb.b) if rgb is not None else None

    def set_entity_color_override(
        self, handle: str, color: int, true_color: Optional[Tuple[int, int, int]]
    ) -> None:
        entity = self._require_entity(handle)
        entity.dxf.color = color
        if true_color is not None:
            entity.rgb = true_color
        else:
            entity.dxf.discard("true_color")

    def clear_entity_color_override(self, handle: str) -> None:
        self.set_entity_color_override(handle, 256, None)

    def find_similar(self, handle: str) -> List[str]:
        reference = self._require_entity(handle)
        ref_type = reference.dxftype()
        ref_layer = reference.dxf.layer
        ref_color = self.get_entity_color(handle)
        return [
            entity.dxf.handle
            for entity in self.modelspace
            if entity.dxftype() == ref_type
            and entity.dxf.layer == ref_layer
            and self.get_entity_color(entity.dxf.handle) == ref_color
        ]

    def add_layer(self, name: str, rgb: Optional[Tuple[int, int, int]] = None) -> None:
        if name in self.layers:
            return
        layer = self.layers.add(name, lineweight=DEFAULT_LAYER_LINEWEIGHT)
        if rgb is not None:
            self._apply_color(layer, rgb)

    def remove_layer(self, name: str) -> None:
        if name == DEFAULT_LAYER_NAME:
            raise ValueError('Layer "0" cannot be deleted.')
        if name not in self.layers:
            return
        self.layers.remove(name)
        if self.active_layer == name:
            self._drawing.header["$CLAYER"] = DEFAULT_LAYER_NAME

    def get_layer_color(self, name: str) -> Tuple[int, int, int]:
        layer = self.layers.get(name)
        rgb = layer.rgb
        if rgb is not None:
            return (rgb.r, rgb.g, rgb.b)
        aci = abs(layer.dxf.color)
        try:
            aci_rgb = ezdxf_colors.aci2rgb(aci)
        except IndexError:
            return (255, 255, 255)
        return (aci_rgb.r, aci_rgb.g, aci_rgb.b)

    def set_layer_color(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self._apply_color(self.layers.get(name), rgb)

    @staticmethod
    def _apply_color(target, rgb: Tuple[int, int, int]) -> None:
        was_off = target.dxf.color < 0
        target.rgb = rgb
        aci = _nearest_aci(rgb)
        target.dxf.color = -aci if was_off else aci

    def is_layer_visible(self, name: str) -> bool:
        return not self.layers.get(name).is_off()

    def set_layer_visible(self, name: str, visible: bool) -> None:
        layer = self.layers.get(name)
        if visible:
            layer.on()
        else:
            layer.off()

    @property
    def active_layer(self) -> str:
        return self._drawing.header.get("$CLAYER", DEFAULT_LAYER_NAME)

    def set_active_layer(self, name: str) -> None:
        self.ensure_layer(name)
        self._drawing.header["$CLAYER"] = name

    def iter_layers(self) -> List[LayerInfo]:
        counts: Dict[str, int] = {}
        for entity in self.modelspace:
            counts[entity.dxf.layer] = counts.get(entity.dxf.layer, 0) + 1
        active = self.active_layer
        infos = [
            LayerInfo(
                name=layer.dxf.name,
                rgb=self.get_layer_color(layer.dxf.name),
                visible=not layer.is_off(),
                is_active=(layer.dxf.name == active),
                entity_count=counts.get(layer.dxf.name, 0),
            )
            for layer in self.layers
        ]
        infos.sort(key=lambda info: (info.name != DEFAULT_LAYER_NAME, info.name.lower()))
        return infos
