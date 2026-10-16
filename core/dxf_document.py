
from __future__ import annotations

import io
import json
import math
import uuid
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import ezdxf
from ezdxf import bbox as ezdxf_bbox, colors as ezdxf_colors, recover
from ezdxf.addons import Importer
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.enums import TextEntityAlignment
from ezdxf.layouts import Modelspace
from ezdxf.math import Matrix44, Vec2
from ezdxf.render import ARROWS
from ezdxf.render.mleader import (
    ConnectionSide,
    HorizontalConnection,
    LeaderType,
    MultiLeaderMTextBuilder,
    TextAlignment,
    VerticalConnection,
)
from ezdxf.sections.tables import LayerTable

from core.detail_view import (
    DETAIL_APPID,
    DetailViewSpec,
    corner_points,
)
from core.detail_view import apply_metadata as apply_detail_metadata
from core.detail_view import metadata_from_entity as detail_metadata_from_entity
from core.detail_view import transform_spec as transform_detail_spec
from core.fonts import (
    DEFAULT_FONT_ID,
    ITALIC_OBLIQUE_ANGLE,
    dxf_font_file,
    ensure_font_renders_distinctly,
    font_id_from_style_name,
    is_italic_style_name,
    text_style_name,
)
from core.generated import GENERATED_APPID
from core.generated import apply_metadata as apply_generated_metadata
from core.generated import mode_from_entity as generated_mode_from_entity
from core.multileader import (
    ARROW_BLOCK_NAMES,
    MULTILEADER_APPID,
    MultileaderSpec,
    MultileaderStyle,
    apply_metadata,
    connection_side,
    dogleg_length,
    leader_vertices,
    legacy_metadata_from_entity,
    metadata_from_entity,
    mtext_content,
    spec_from_native,
    style_from_metadata,
    style_metadata,
    text_alignment,
    text_from_mtext,
    transform_spec,
    with_identifier,
)

_MLEADER_STYLES_KEY = "GSG_MLEADER_STYLES"
_CURRENT_MLEADER_STYLE_KEY = "GSG_CMLEADERSTYLE"

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
# $INSUNITS / BLOCK_RECORD insertion-unit code for millimetres.
INSUNITS_MILLIMETERS = 4
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
        doc._migrate_legacy_multileaders()
        return doc

    @classmethod
    def from_text(cls, content: str) -> "DXFDocument":
        try:
            drawing = ezdxf.read(io.StringIO(content))
        except ezdxf.DXFStructureError:
            drawing, _auditor = recover.read(io.BytesIO(content.encode("utf-8", errors="surrogateescape")))
        doc = cls(drawing)
        doc._ensure_all_referenced_layers()
        doc._migrate_legacy_multileaders()
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

    def ensure_text_style(self, font_id: str, italic: bool = False) -> str:
        ensure_font_renders_distinctly(font_id, italic)
        style_name = text_style_name(font_id, italic)
        if style_name not in self._drawing.styles:
            dxfattribs = {"font": dxf_font_file(font_id, italic)}
            if italic:
                dxfattribs["oblique"] = ITALIC_OBLIQUE_ANGLE
            self._drawing.styles.new(style_name, dxfattribs=dxfattribs)
        return style_name

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
        font_id: str = DEFAULT_FONT_ID,
        italic: bool = False,
        lineweight_mm: Optional[float] = None,
    ) -> str:
        self.ensure_layer(layer)
        style_name = self.ensure_text_style(font_id, italic)
        dxfattribs = {"layer": layer, "insert": insert, "style": style_name}
        if lineweight_mm is not None:
            dxfattribs["lineweight"] = round(lineweight_mm * 100)
        entity = self.modelspace.add_text(
            text,
            height=height,
            rotation=rotation,
            dxfattribs=dxfattribs,
        )
        alignment = _TEXT_ALIGNMENTS.get((halign, valign))
        if alignment is not None and alignment is not TextEntityAlignment.BOTTOM_LEFT:
            entity.set_placement(insert, align=alignment)
        return entity.dxf.handle

    def block_names(self) -> List[str]:
        """The blocks a user could place from this drawing, by name.

        Layouts, anonymous blocks (hatch patterns, dimensions) and external references
        are the drawing's own plumbing rather than something to insert, so they are left out.
        """
        names = [
            block.name
            for block in self._drawing.blocks
            if not block.name.startswith("*")
            and not block.is_any_layout
            and not block.block.is_anonymous
            and not block.block.is_xref
        ]
        return sorted(names, key=str.casefold)

    def has_block(self, name: str) -> bool:
        return name in self._drawing.blocks

    def import_block(self, name: str, source: Drawing) -> None:
        """Define `name` from a block file, unless the drawing already defines it.

        A block file is a drawing whose modelspace is the block and whose $INSBASE is its
        base point - what AutoCAD's WBLOCK writes. An existing definition wins, as it does
        in AutoCAD, so blocks already placed from it never change shape underneath the user.
        """
        if self.has_block(name):
            return
        block = self._drawing.blocks.new(name=name, base_point=source.header.get("$INSBASE", (0.0, 0.0, 0.0)))
        block.block_record.dxf.units = int(source.header.get("$INSUNITS", 0))
        importer = Importer(source, self._drawing)
        importer.import_entities(source.modelspace(), block)
        importer.finalize()

    def block_is_paper_sized(self, name: str) -> bool:
        """Whether a block is drawn in paper millimetres - a symbol sized for the sheet
        rather than an object at its true size on the ground."""
        return self._drawing.blocks[name].block_record.dxf.get("units", 0) == INSUNITS_MILLIMETERS

    def add_block_reference(
        self,
        name: str,
        insert: Sequence[float],
        rotation: float = 0.0,
        scale: float = 1.0,
        layer: str = "0",
    ) -> str:
        self.ensure_layer(layer)
        entity = self.modelspace.add_blockref(
            name,
            insert,
            dxfattribs={"layer": layer, "rotation": rotation, "xscale": scale, "yscale": scale, "zscale": scale},
        )
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

    def add_multileader(self, spec: MultileaderSpec) -> str:
        spec = spec.normalized()
        self.ensure_layer(spec.layer)
        if MULTILEADER_APPID not in self._drawing.appids:
            self._drawing.appids.add(MULTILEADER_APPID)
        style_name = spec.style_name if spec.style_name in self._drawing.mleader_styles else "Standard"
        builder = self.modelspace.add_multileader_mtext(style_name, dxfattribs={"layer": spec.layer})
        entity = builder.multileader
        self._build_multileader(entity, spec)
        return entity.dxf.handle

    def rebuild_multileader(self, handle: str, spec: MultileaderSpec) -> None:
        spec = spec.normalized()
        entity = self._require_entity(handle)
        self.ensure_layer(spec.layer)
        entity.dxf.layer = spec.layer
        style = self._drawing.mleader_styles.get(spec.style_name) or self._drawing.mleader_styles.get("Standard")
        entity.dxf.style_handle = style.dxf.handle
        self._build_multileader(entity, spec)

    def _linetype_name(self, name: str) -> str:
        return name if name in self._drawing.linetypes else "ByBlock"

    def _arrow_handle(self, arrowhead: str, arrow_block: str) -> Optional[str]:
        if arrow_block and self.has_block(arrow_block):
            return self._drawing.blocks.get(arrow_block).block_record_handle
        name = ARROW_BLOCK_NAMES.get(arrowhead, "")
        if not name:
            return None
        return ARROWS.arrow_handle(self._drawing.blocks, name)

    def _build_multileader(self, entity, spec: MultileaderSpec) -> None:
        builder = MultiLeaderMTextBuilder(entity)
        builder.set_overall_scaling(spec.scale)
        builder.set_content(
            mtext_content(spec),
            color=spec.text_color if spec.text_color is not None else ezdxf_colors.BYBLOCK,
            char_height=spec.height,
            alignment=TextAlignment[text_alignment(spec)],
            style=self.ensure_text_style(spec.font, spec.italic),
        )
        builder.set_leader_properties(
            color=spec.leader_color if spec.leader_color is not None else ezdxf_colors.BYBLOCK,
            linetype=self._linetype_name(spec.leader_linetype),
            lineweight=spec.leader_lineweight,
            leader_type=LeaderType.splines if spec.line_type == "spline" else LeaderType.straight_lines,
        )
        builder.set_arrow_properties(size=spec.effective_arrow_size)
        arrow_handle = self._arrow_handle(spec.arrowhead, spec.arrow_block)
        if arrow_handle is not None:
            entity.dxf.arrow_head_handle = arrow_handle
        builder.set_connection_types(
            left=HorizontalConnection[spec.left_connection],
            right=HorizontalConnection[spec.right_connection],
            top=VerticalConnection[spec.top_connection],
            bottom=VerticalConnection[spec.bottom_connection],
        )
        builder.set_connection_properties(
            landing_gap=spec.gap / spec.scale,
            dogleg_length=dogleg_length(spec) / spec.scale,
        )
        mtext = builder.context.mtext
        mtext.line_spacing_factor = spec.line_spacing
        mtext.has_bg_fill = int(spec.background)
        mtext.use_window_bg_color = int(spec.background)
        mtext.bg_scale_factor = spec.background_scale
        builder.add_leader_line(ConnectionSide[connection_side(spec)], [Vec2(point) for point in leader_vertices(spec)])
        builder.build(Vec2(0.0, 0.0), rotation=spec.rotation)
        offset = self._multileader_connection(entity)
        builder.build(Vec2(spec.text_position) - offset, rotation=spec.rotation)
        entity.dxf.has_text_frame = int(spec.text_frame)
        entity.dxf.has_landing = int(spec.has_landing)
        if not spec.text:
            entity.dxf.content_type = 0
            entity.context.mtext = None
        apply_metadata(entity, spec)

    @staticmethod
    def _multileader_connection(entity) -> Vec2:
        leader = entity.context.leaders[0]
        point = leader.last_leader_point
        if entity.dxf.get("has_dogleg", 0):
            point = point + leader.dogleg_vector * leader.dogleg_length
        return Vec2(point)

    def _style_from_native(self, name: str, style) -> MultileaderStyle:
        dxf = style.dxf
        return MultileaderStyle(
            name=name,
            line_type="spline" if dxf.get("leader_type", 1) == 2 else "straight",
            height=float(dxf.get("char_height", 0.6)) or 0.6,
            gap=float(dxf.get("landing_gap_size", 0.18)),
            landing_length=float(dxf.get("dogleg_length", 0.0)),
            scale=float(dxf.get("scale", 1.0)) or 1.0,
            annotative=bool(dxf.get("is_annotative", 0)),
            arrow_size=float(dxf.get("arrow_head_size", 0.0)),
            landing_enabled=bool(dxf.get("has_dogleg", 1)),
        ).normalized()

    def multileader_styles(self) -> Dict[str, MultileaderStyle]:
        styles: Dict[str, MultileaderStyle] = {}
        for name, style in self._drawing.mleader_styles:
            parsed = None
            if style.has_xdata(MULTILEADER_APPID):
                parsed = style_from_metadata(style.get_xdata(MULTILEADER_APPID))
            styles[name] = parsed if parsed is not None else self._style_from_native(name, style)
        return styles

    def set_multileader_styles(self, styles: Dict[str, MultileaderStyle]) -> None:
        if MULTILEADER_APPID not in self._drawing.appids:
            self._drawing.appids.add(MULTILEADER_APPID)
        table = self._drawing.mleader_styles
        for name in [name for name, _style in table]:
            if name not in styles and name != "Standard":
                table.delete(name)
        for style in styles.values():
            self._write_native_style(style.normalized())

    def _write_native_style(self, style: MultileaderStyle) -> None:
        table = self._drawing.mleader_styles
        native = table.get(style.name)
        if native is None:
            native = table.duplicate_entry("Standard", style.name)
        dxf = native.dxf
        dxf.content_type = 2
        dxf.leader_type = 2 if style.line_type == "spline" else 1
        dxf.leader_line_color = ezdxf_colors.encode_raw_color(
            style.leader_color if style.leader_color is not None else ezdxf_colors.BYBLOCK
        )
        dxf.leader_lineweight = style.leader_lineweight
        dxf.leader_linetype_handle = self._drawing.linetypes.get(self._linetype_name(style.leader_linetype)).dxf.handle
        dxf.arrow_head_size = style.arrow_size or style.height * 0.9
        arrow_handle = self._arrow_handle(style.arrowhead, style.arrow_block)
        if arrow_handle is None:
            dxf.discard("arrow_head_handle")
        else:
            dxf.arrow_head_handle = arrow_handle
        dxf.char_height = style.height
        dxf.landing_gap_size = style.gap
        dxf.has_dogleg = int(style.landing_enabled)
        dxf.has_landing = int(style.landing_enabled)
        dxf.dogleg_length = style.landing_length
        dxf.text_color = ezdxf_colors.encode_raw_color(
            style.text_color if style.text_color is not None else ezdxf_colors.BYBLOCK
        )
        dxf.text_style_handle = self._drawing.styles.get(self.ensure_text_style(style.font, style.italic)).dxf.handle
        dxf.text_left_attachment_type = int(HorizontalConnection[style.left_connection])
        dxf.text_right_attachment_type = int(HorizontalConnection[style.right_connection])
        dxf.text_top_attachment_type = int(VerticalConnection[style.top_connection])
        dxf.text_bottom_attachment_type = int(VerticalConnection[style.bottom_connection])
        dxf.text_attachment_direction = 1 if style.direction == "vertical" else 0
        dxf.has_text_frame = int(style.text_frame)
        dxf.first_segment_angle_constraint = math.radians(style.first_angle)
        dxf.second_segment_angle_constraint = math.radians(style.second_angle)
        dxf.max_leader_segments_points = 3
        dxf.is_annotative = int(style.annotative)
        dxf.scale = style.scale
        native.set_xdata(MULTILEADER_APPID, style_metadata(style))

    def multileaders_using_style(self, name: str) -> List[str]:
        handles: List[str] = []
        for entity in self.modelspace:
            metadata = metadata_from_entity(entity)
            if metadata is not None and metadata[1].style_name == name:
                handles.append(entity.dxf.handle)
        return handles

    def multileader_spec(self, handle: str) -> Optional[MultileaderSpec]:
        metadata = self.multileader_metadata(handle)
        return metadata[1] if metadata is not None else None

    def defined_multileader_style(self, name: str) -> Optional[MultileaderStyle]:
        style = self._drawing.mleader_styles.get(name)
        if style is None or not style.has_xdata(MULTILEADER_APPID):
            return None
        return style_from_metadata(style.get_xdata(MULTILEADER_APPID))

    @property
    def current_multileader_style(self) -> str:
        entry = self._drawing.rootdict.get(_CURRENT_MLEADER_STYLE_KEY)
        name = str(entry.dxf.value) if entry is not None else "Standard"
        return name if name in self._drawing.mleader_styles else "Standard"

    def set_current_multileader_style(self, name: str) -> None:
        rootdict = self._drawing.rootdict
        entry = rootdict.get(_CURRENT_MLEADER_STYLE_KEY)
        if entry is None:
            rootdict.add_dict_var(_CURRENT_MLEADER_STYLE_KEY, name)
        else:
            entry.dxf.value = name

    def linetype_names(self) -> List[str]:
        return [linetype.dxf.name for linetype in self._drawing.linetypes]

    def _migrate_legacy_multileaders(self) -> None:
        groups: Dict[str, Tuple[List[DXFGraphic], Optional[MultileaderSpec]]] = {}
        for entity in self.modelspace:
            legacy = legacy_metadata_from_entity(entity)
            if legacy is None:
                continue
            identifier, role, spec = legacy
            members, text_spec = groups.get(identifier, ([], None))
            members.append(entity)
            groups[identifier] = (members, spec if role == "text" or text_spec is None else text_spec)
        for identifier, (members, spec) in groups.items():
            for entity in members:
                self.modelspace.delete_entity(entity)
            if spec is not None:
                self.add_multileader(with_identifier(spec, identifier))
        rootdict = self._drawing.rootdict
        entry = rootdict.get(_MLEADER_STYLES_KEY)
        if entry is None:
            return
        try:
            legacy_styles = [MultileaderStyle.from_payload(payload) for payload in json.loads(entry.dxf.value)]
        except (AttributeError, KeyError, TypeError, ValueError):
            legacy_styles = []
        rootdict.discard(_MLEADER_STYLES_KEY)
        if legacy_styles:
            styles = self.multileader_styles()
            styles.update({style.name: style for style in legacy_styles if style.name})
            self.set_multileader_styles(styles)

    def mark_generated(self, handle: str, mode: str) -> None:
        """Record that the generator drew this entity for `mode`."""
        if GENERATED_APPID not in self._drawing.appids:
            self._drawing.appids.add(GENERATED_APPID)
        apply_generated_metadata(self._require_entity(handle), mode)

    def generated_handles(self, modes: Iterable[str]) -> List[str]:
        """Everything the generator drew for any of `modes`, in drawing order."""
        wanted = set(modes)
        if not wanted:
            return []
        return [
            entity.dxf.handle
            for entity in self.modelspace
            if generated_mode_from_entity(entity) in wanted
        ]

    def is_multileader(self, handle: str) -> bool:
        entity = self.get_entity(handle)
        return entity is not None and entity.dxftype() == "MULTILEADER"

    def is_own_multileader(self, handle: str) -> bool:
        entity = self.get_entity(handle)
        return entity is not None and entity.dxftype() == "MULTILEADER" and metadata_from_entity(entity) is not None

    def snapshot_multileader(self, handle: str) -> DXFGraphic:
        return self._require_entity(handle).copy()

    def restore_multileader(self, handle: str, snapshot: DXFGraphic) -> None:
        entity = self._require_entity(handle)
        kept = {"handle", "owner"}
        original = snapshot.dxf.all_existing_dxf_attribs()
        for key in list(entity.dxf.all_existing_dxf_attribs()):
            if key not in kept and key not in original:
                entity.dxf.discard(key)
        for key, value in original.items():
            if key not in kept:
                entity.dxf.set(key, value)
        snapshot.copy_data(entity)
        if snapshot.has_xdata(MULTILEADER_APPID):
            entity.set_xdata(MULTILEADER_APPID, list(snapshot.get_xdata(MULTILEADER_APPID)))
        else:
            entity.discard_xdata(MULTILEADER_APPID)

    def multileader_metadata(self, handle: str) -> Optional[Tuple[str, MultileaderSpec]]:
        entity = self.get_entity(handle)
        if entity is None or entity.dxftype() != "MULTILEADER":
            return None
        metadata = metadata_from_entity(entity)
        if metadata is not None:
            return metadata
        spec = spec_from_native(entity)
        return (spec.identifier, spec) if spec is not None else None

    def multileader_handles(self, handle: str) -> List[str]:
        return [handle]

    def expand_annotation_handles(self, handles: Iterable[str]) -> List[str]:
        expanded: List[str] = []
        for handle in handles:
            if handle not in expanded:
                expanded.append(handle)
        return expanded

    def multileader_text_handle(self, handles: Iterable[str]) -> Optional[str]:
        unique = set(handles)
        if len(unique) != 1:
            return None
        handle = unique.pop()
        return handle if self.is_multileader(handle) else None

    def multileader_text(self, handle: str) -> str:
        mtext = self._require_entity(handle).context.mtext
        return text_from_mtext(mtext.default_content) if mtext is not None else ""

    def multileader_grips(self, handle: str) -> List[Tuple[float, float]]:
        spec = self.multileader_spec(handle)
        if spec is None:
            return []
        grips = [spec.tip]
        if spec.has_landing:
            grips.append(spec.landing)
        grips.append(spec.text_position)
        return grips

    def separate_multileader_groups(self, handles: Iterable[str], dx: float = 0.0, dy: float = 0.0) -> None:
        for handle in handles:
            if not self.is_own_multileader(handle):
                continue
            spec = self.multileader_spec(handle)
            moved = transform_spec(spec, lambda point: (point[0] + dx, point[1] + dy)) if dx or dy else spec
            self.rebuild_multileader(handle, with_identifier(moved, uuid.uuid4().hex))

    def _transform_multileaders(
        self, handles: Iterable[str], transform, length_factor: float = 1.0, rotation_delta: float = 0.0
    ) -> None:
        for handle in handles:
            if self.is_own_multileader(handle):
                spec = self.multileader_spec(handle)
                self.rebuild_multileader(handle, transform_spec(spec, transform, length_factor, rotation_delta))

    def translate_entities(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            if not self.is_own_multileader(handle):
                self.translate_entity(handle, dx, dy, dz)
        self._transform_multileaders(resolved, lambda point: (point[0] + dx, point[1] + dy))
        self._transform_detail_metadata(resolved, lambda point: (point[0] + dx, point[1] + dy))
        return resolved

    def rotate_entities(self, handles: Iterable[str], angle: float, center: Sequence[float]) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            if not self.is_own_multileader(handle):
                self.rotate_entity(handle, angle, center)
        radians = math.radians(angle)
        cos_a, sin_a = math.cos(radians), math.sin(radians)
        cx, cy = center[0], center[1]
        rotate = lambda point: (
            cx + (point[0] - cx) * cos_a - (point[1] - cy) * sin_a,
            cy + (point[0] - cx) * sin_a + (point[1] - cy) * cos_a,
        )
        self._transform_multileaders(resolved, rotate, rotation_delta=angle)
        self._transform_detail_metadata(resolved, rotate, rotation_delta=angle)
        return resolved

    def scale_entities(self, handles: Iterable[str], factor: float, center: Sequence[float]) -> List[str]:
        resolved = self.expand_annotation_handles(handles)
        for handle in resolved:
            if not self.is_own_multileader(handle):
                self.scale_entity(handle, factor, center)
        cx, cy = center[0], center[1]
        resize = lambda point: (cx + (point[0] - cx) * factor, cy + (point[1] - cy) * factor)
        self._transform_multileaders(resolved, resize, factor)
        self._transform_detail_metadata(resolved, resize, factor)
        return resolved

    def add_detail_view(self, spec: DetailViewSpec) -> str:
        spec = spec.normalized()
        self.ensure_layer(spec.layer)
        if DETAIL_APPID not in self._drawing.appids:
            self._drawing.appids.add(DETAIL_APPID)
        handle = self.add_lwpolyline(corner_points(spec), spec.layer, closed=True)
        apply_detail_metadata(self._require_entity(handle), spec)
        return handle

    def detail_view_spec(self, handle: str) -> Optional[DetailViewSpec]:
        entity = self.get_entity(handle)
        return detail_metadata_from_entity(entity) if entity is not None else None

    def iter_detail_views(self) -> List[Tuple[str, DetailViewSpec]]:
        found: List[Tuple[str, DetailViewSpec]] = []
        for entity in self.modelspace:
            spec = detail_metadata_from_entity(entity)
            if spec is not None:
                found.append((entity.dxf.handle, spec))
        return found

    def set_detail_view_spec(self, handle: str, spec: DetailViewSpec) -> None:
        spec = spec.normalized()
        entity = self._require_entity(handle)
        entity.set_points(corner_points(spec), format="xy")
        entity.close(True)
        apply_detail_metadata(entity, spec)

    def _transform_detail_metadata(
        self, handles: Iterable[str], transform, length_factor: float = 1.0, rotation_delta: float = 0.0
    ) -> None:
        for handle in handles:
            entity = self.get_entity(handle)
            if entity is None:
                continue
            spec = detail_metadata_from_entity(entity)
            if spec is None:
                continue
            moved = transform_detail_spec(spec, transform, length_factor, rotation_delta)
            entity.set_points(corner_points(moved), format="xy")
            entity.close(True)
            apply_detail_metadata(entity, moved)

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

    def entities_bbox(
        self, handles: Iterable[str]
    ) -> Optional[Tuple[Tuple[float, float], Tuple[float, float]]]:
        """The outline around everything named - where a transform gizmo goes."""
        entities = [entity for handle in handles if (entity := self.get_entity(handle)) is not None]
        if not entities:
            return None
        box = ezdxf_bbox.extents(entities)
        if not box.has_data:
            return None
        return (box.extmin.x, box.extmin.y), (box.extmax.x, box.extmax.y)

    def get_text_content(self, handle: str) -> str:
        return self._require_entity(handle).dxf.text

    def set_text_content(self, handle: str, text: str) -> None:
        self._require_entity(handle).dxf.text = text

    def get_text_height(self, handle: str) -> float:
        return self._require_entity(handle).dxf.height

    def set_text_height(self, handle: str, height: float) -> None:
        self._require_entity(handle).dxf.height = height

    def text_anchor(self, handle: str) -> Tuple[float, float]:
        """The point a text hangs from - and turns around.

        Only plain baseline-left text uses its insertion point; give it any other
        alignment and the alignment point takes over.
        """
        entity = self._require_entity(handle)
        halign, valign = entity.dxf.get("halign", 0), entity.dxf.get("valign", 0)
        point = entity.dxf.insert if halign == 0 and valign == 0 else entity.dxf.get(
            "align_point", entity.dxf.insert
        )
        return point.x, point.y

    def get_text_rotation(self, handle: str) -> float:
        return self._require_entity(handle).dxf.rotation

    def set_text_rotation(self, handle: str, rotation: float) -> None:
        self._require_entity(handle).dxf.rotation = rotation

    def get_text_font(self, handle: str) -> str:
        return font_id_from_style_name(self._require_entity(handle).dxf.style)

    def set_text_font(self, handle: str, font_id: str) -> None:
        style_name = self.ensure_text_style(font_id, self.get_text_italic(handle))
        self._require_entity(handle).dxf.style = style_name

    def get_text_italic(self, handle: str) -> bool:
        return is_italic_style_name(self._require_entity(handle).dxf.style)

    def set_text_italic(self, handle: str, italic: bool) -> None:
        style_name = self.ensure_text_style(self.get_text_font(handle), italic)
        self._require_entity(handle).dxf.style = style_name

    def get_text_lineweight_mm(self, handle: str) -> Optional[float]:
        lineweight = self._require_entity(handle).dxf.lineweight
        return None if lineweight < 0 else lineweight / 100.0

    def set_text_lineweight_mm(self, handle: str, lineweight_mm: Optional[float]) -> None:
        self._require_entity(handle).dxf.lineweight = (
            -1 if lineweight_mm is None else round(lineweight_mm * 100)
        )

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

    def all_text_handles(self) -> List[str]:
        return [entity.dxf.handle for entity in self.modelspace if entity.dxftype() == "TEXT"]

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
