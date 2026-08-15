"""Wraps a single ezdxf `Drawing` and is the only place in `core/` (or `ui/`)
that mutates one — every edit command goes through this class so undo/redo
stays correct and ezdxf's entity-lifecycle rules (see `unlink_entity`/
`restore_entity` below) are only ever handled in one place.

Reading a DXF for the read-only preview (`ui/dxf_viewer.py`'s rendering via
`ezdxf.addons.drawing`) still touches the raw `Drawing` through the `.drawing`
escape hatch — that's display, not mutation, so it doesn't need to go through
the methods below.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Modelspace
from ezdxf.sections.tables import LayerTable

DEFAULT_LAYER_NAME = "0"


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

    def _ensure_all_referenced_layers(self) -> None:
        """Some real-world DXF files (e.g. exports from surveying/cadastral
        software) have entities referencing a layer name that was never
        given its own LAYER table entry — valid DXF; AutoCAD just
        auto-materializes a default entry for those on open. Do the same
        here at load time, so every layer something is actually drawn on
        shows up in `iter_layers()` and can be toggled/recolored/deleted
        like any other, instead of being invisible to the layers panel."""
        for entity in self.modelspace:
            self.ensure_layer(entity.dxf.layer)

    def save(self, file_path: str) -> None:
        self._drawing.saveas(file_path)

    @property
    def drawing(self) -> Drawing:
        """Escape hatch for the renderer — never mutate through this."""
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
        """Creates the LAYER table entry for `name` if it doesn't exist yet.

        ezdxf lets an entity reference a layer name with no table entry, but
        every command that targets a layer calls this first so the document
        stays well-formed (and the layer shows up in layer lists/colors).
        """
        if name not in self.layers:
            self.layers.add(name)

    # ------------------------------------------------------------------
    # Draw primitives — each returns the new entity's handle. Coordinates
    # accept either 2D (x, y) or 3D (x, y, z) tuples — ezdxf's own entity
    # methods take either natively, so no conversion is needed here.
    # ------------------------------------------------------------------
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
        """A single 2D LWPOLYLINE entity through `points` (elevation, if any
        z is given, is not used — LWPOLYLINE is inherently planar)."""
        self.ensure_layer(layer)
        entity = self.modelspace.add_lwpolyline(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    def add_polyline3d(self, points: Iterable[Sequence[float]], layer: str = "0", closed: bool = False) -> str:
        """A single 3D POLYLINE entity through `points` (each a full x, y, z)."""
        self.ensure_layer(layer)
        entity = self.modelspace.add_polyline3d(points, close=closed, dxfattribs={"layer": layer})
        return entity.dxf.handle

    # ------------------------------------------------------------------
    # Reversible delete: unlink keeps the entity alive in the entity
    # database (just detached from the layout), so restore can put the
    # exact same object — same handle — back rather than recreating it.
    # ------------------------------------------------------------------
    def unlink_entity(self, handle: str) -> DXFGraphic:
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        self.modelspace.unlink_entity(entity)
        return entity

    def restore_entity(self, entity: DXFGraphic) -> None:
        self.modelspace.add_entity(entity)

    def translate_entity(self, handle: str, dx: float, dy: float, dz: float = 0.0) -> None:
        """Moves one entity by (dx, dy, dz) in place. Exactly reversible by
        translating again with the negated vector — used by MoveCommand."""
        entity = self.get_entity(handle)
        if entity is None:
            raise KeyError(f"No entity with handle {handle!r}")
        entity.translate(dx, dy, dz)

    # ------------------------------------------------------------------
    # Layers — visibility/color/active-layer/delete. New entities always
    # get their layer table entry created first (see `ensure_layer` above);
    # these methods assume the layer already exists unless noted.
    # ------------------------------------------------------------------
    def add_layer(self, name: str, rgb: Optional[Tuple[int, int, int]] = None) -> None:
        if name in self.layers:
            return
        layer = self.layers.add(name)
        if rgb is not None:
            layer.rgb = rgb

    def remove_layer(self, name: str) -> None:
        """Removes the layer table entry. Does not touch entities still on
        that layer — callers that want a clean document (e.g. DeleteLayerCommand)
        remove those entities first."""
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
        if rgb is None:
            return (255, 255, 255)
        return (rgb.r, rgb.g, rgb.b)

    def set_layer_color(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self.layers.get(name).rgb = rgb

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
        """The current/active layer — DXF's own $CLAYER header var. New
        entities drawn interactively default onto this layer."""
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
