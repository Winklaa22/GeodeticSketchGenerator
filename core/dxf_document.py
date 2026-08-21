
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import colors as ezdxf_colors, recover
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Modelspace
from ezdxf.sections.tables import LayerTable

DEFAULT_LAYER_NAME = "0"


@lru_cache(maxsize=None)
def _nearest_aci(rgb: Tuple[int, int, int]) -> int:
    """The AutoCAD Color Index (1-255) whose RGB is closest to `rgb` — used
    as a fallback alongside true-color (see `DXFDocument._apply_color`)."""
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
    """A snapshot of one layer's state, for the UI layer panel — plain data,
    no ezdxf objects, so it stays cheap to compare/rebuild rows from."""

    name: str
    rgb: Tuple[int, int, int]
    visible: bool
    is_active: bool
    entity_count: int


class DXFDocument:
    """A live, editable DXF document."""

    def __init__(self, drawing: Drawing) -> None:
        self._drawing = drawing

    @classmethod
    def new(cls) -> "DXFDocument":
        """A blank document, same defaults as a new AutoCAD drawing."""
        return cls(ezdxf.new())

    @classmethod
    def load(cls, file_path: str) -> "DXFDocument":
        """Loads `file_path`, recovering from a malformed DXF where possible.

        Raises `IOError`/`ezdxf.DXFError` (the caller is expected to catch
        these — see `ui/dxf_viewer.py`'s `DxfViewer.load_file`).
        """
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
            self.layers.add(name)

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
    ) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_text(
            text, height=height, rotation=rotation, dxfattribs={"layer": layer, "insert": insert}
        )
        return entity.dxf.handle

    def add_lwpolyline(self, points: Iterable[Sequence[float]], layer: str = "0", closed: bool = False) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_lwpolyline(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_polyline3d(self, points: Iterable[Sequence[float]], layer: str = "0", closed: bool = False) -> str:
        """A single 3D POLYLINE entity through `points` (each a full x, y, z)."""
        self.ensure_layer(layer)
        entity = self.modelspace.add_polyline3d(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def unlink_entity(self, handle: str) -> DXFGraphic:
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        self.modelspace.unlink_entity(entity)
        return entity

    def restore_entity(self, entity: DXFGraphic) -> None:
        self.modelspace.add_entity(entity)

    def translate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> None:
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        entity.translate(dx, dy, dz)

    # -- Layers — visibility/color/active-layer/delete --------------------
    def add_layer(self, name: str, rgb: Optional[Tuple[int, int, int]] = None) -> None:
        if name in self.layers:
            return
        layer = self.layers.add(name)
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
        aci = abs(layer.dxf.color)  # a negative stored value means "off", not a different color
        try:
            aci_rgb = ezdxf_colors.aci2rgb(aci)
        except IndexError:
            return (255, 255, 255)
        return (aci_rgb.r, aci_rgb.g, aci_rgb.b)

    def set_layer_color(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self._apply_color(self.layers.get(name), rgb)

    @staticmethod
    def _apply_color(layer, rgb: Tuple[int, int, int]) -> None:
        was_off = layer.dxf.color < 0
        layer.rgb = rgb
        aci = _nearest_aci(rgb)
        layer.dxf.color = -aci if was_off else aci

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
        """A snapshot of every layer for the UI panel, layer "0" first, then
        alphabetical."""
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
