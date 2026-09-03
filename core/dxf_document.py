
from __future__ import annotations

import io
import math
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
        if entity.dxf.color in (0, 256):
            return self.get_layer_color(entity.dxf.layer)
        rgb = entity.rgb
        if rgb is not None:
            return (rgb.r, rgb.g, rgb.b)
        try:
            aci_rgb = ezdxf_colors.aci2rgb(abs(entity.dxf.color))
        except IndexError:
            return (255, 255, 255)
        return (aci_rgb.r, aci_rgb.g, aci_rgb.b)

    def set_entity_color(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self._apply_color(self._require_entity(handle), rgb)

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
