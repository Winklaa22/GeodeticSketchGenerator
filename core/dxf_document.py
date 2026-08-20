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
        """The counterpart to `to_text()` — loads a document from embedded
        DXF text (see core.project's ProjectState.dxf_content) rather than
        a file on disk, recovering from a malformed document the same way
        `load()` does.

        Raises `ezdxf.DXFError` (the caller is expected to catch it — see
        `ui/dxf_viewer.py`'s `DxfViewer.load_from_text`).
        """
        try:
            drawing = ezdxf.read(io.StringIO(content))
        except ezdxf.DXFStructureError:
            drawing, _auditor = recover.read(io.BytesIO(content.encode("utf-8", errors="surrogateescape")))
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

    def to_text(self) -> str:
        """The document's content as plain ASCII DXF text — the counterpart
        to `from_text()`, used to embed a full DXF snapshot directly inside
        a saved project file (see core.project) rather than requiring the
        document to have been saved to its own .dxf file first."""
        stream = io.StringIO()
        self._drawing.write(stream)
        return stream.getvalue()

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
            self._apply_color(layer, rgb)

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
        """The layer's color as plain RGB, for the layer panel's swatch.

        Most real-world DXFs (including typical cadastral/surveying
        exports) color their layers the classic way — an AutoCAD Color
        Index (ACI) in `dxf.color` — rather than a true-color RGB value.
        `Layer.rgb` only reflects the latter and is `None` for an
        ACI-colored layer, which used to make every such layer's swatch
        show up plain white here even though the canvas (whose renderer
        already resolves ACI correctly) showed its real color."""
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
        """Sets both the modern true-color (DXF group 420) and the closest
        classic AutoCAD Color Index (group 62) for `layer`.

        True-color is what `get_layer_color` prefers, so it wins whenever
        it survives — but plenty of real-world DXFs (older AutoCAD exports,
        and many legacy surveying/cadastral tools) predate true-color
        support entirely (added in AC1018/2004). Writing one of those back
        out silently drops group 420 - ezdxf won't export an attribute a
        DXF version doesn't support - which would lose the color outright
        if the classic ACI index weren't also set as a fallback.

        A layer being off is *also* stored in this same group 62 (as a
        negative color index), so the sign is preserved rather than always
        writing positive - otherwise recoloring a hidden layer would
        silently turn it back on.
        """
        was_off = layer.is_off()
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
