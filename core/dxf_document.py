
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import colors as ezdxf_colors, recover
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Modelspace
from ezdxf.math import Matrix44
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

    def _require_entity(self, handle: str) -> DXFGraphic:
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        return entity

    def unlink_entity(self, handle: str) -> Optional[DXFGraphic]:
        """Unlinks the entity at `handle`, keeping it alive in the entity
        database so a later `relink_entity`/`restore_entity` can bring back
        the exact same object. Returns None, rather than raising, for a
        handle that's already not linked into the model space — a
        `Command` that captures handles once (DeleteEntityCommand) can be
        replayed against a handle that another Command's own undo/redo has
        since unlinked out from under it."""
        entity = self.get_entity(handle)
        if entity is None or entity.get_layout() is None:
            return None
        self.modelspace.unlink_entity(entity)
        return entity

    def restore_entity(self, entity: DXFGraphic) -> None:
        self.modelspace.add_entity(entity)

    def relink_entity(self, handle: str) -> None:
        """Re-links a previously unlinked entity back into the model space
        by its original handle, if it isn't linked already — used by a
        creating Command's own redo (a second execute()) so it reuses the
        exact same entity/handle instead of making a new one, which would
        otherwise leave any other Command that still names the old handle
        (e.g. a DeleteEntityCommand higher up the undo stack) pointing at
        nothing once replayed."""
        entity = self.get_entity(handle)
        if entity is not None and entity.get_layout() is None:
            self.modelspace.add_entity(entity)

    def translate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> None:
        self._require_entity(handle).translate(dx, dy, dz)

    def duplicate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> str:
        """Copies the entity at `handle`, offsetting the copy by (dx, dy, dz)
        so it lands next to the original rather than exactly on top of it —
        used for Ctrl+D (duplicate) and Ctrl+V (paste)."""
        copy = self._require_entity(handle).copy()
        copy.translate(dx, dy, dz)
        self.modelspace.add_entity(copy)
        return copy.dxf.handle

    def rotate_entity(self, handle: str, angle: float, center: Sequence[float]) -> None:
        """Rotates the entity at `handle` by `angle` degrees (positive =
        counter-clockwise, same convention as AutoCAD's ROTATE) around
        `center`."""
        cx, cy = center[0], center[1]
        matrix = Matrix44.chain(
            Matrix44.translate(-cx, -cy, 0),
            Matrix44.z_rotate(math.radians(angle)),
            Matrix44.translate(cx, cy, 0),
        )
        self._require_entity(handle).transform(matrix)

    def scale_entity(self, handle: str, factor: float, center: Sequence[float]) -> None:
        """Scales the entity at `handle` by `factor` (uniformly, in X/Y)
        around `center` — same convention as AutoCAD's SCALE. Z is left
        untouched, same "purely in-plane" choice as `rotate_entity` (a real
        elevation shouldn't shift just because something on the same layer
        got resized)."""
        cx, cy = center[0], center[1]
        matrix = Matrix44.chain(
            Matrix44.translate(-cx, -cy, 0),
            Matrix44.scale(factor, factor, 1.0),
            Matrix44.translate(cx, cy, 0),
        )
        self._require_entity(handle).transform(matrix)

    # -- TEXT entity properties — content/height/rotation/color -----------
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
        """The entity's *effective* color: its own override if it has one,
        otherwise its layer's (DXF's "ByLayer" default, color 256)."""
        entity = self._require_entity(handle)
        if entity.dxf.color in (0, 256):  # ByBlock / ByLayer — no override set
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
    def _apply_color(target, rgb: Tuple[int, int, int]) -> None:
        """Sets both true-color and its nearest-ACI fallback on a layer or
        an entity — see `_nearest_aci`. Only a *layer's* stored color can
        ever be negative (meaning "off"), and that sign is preserved."""
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
