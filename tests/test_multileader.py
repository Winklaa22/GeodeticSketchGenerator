from __future__ import annotations

import json
import math

import pytest
from ezdxf.render import ARROWS

from core.commands.edit import DeleteEntityCommand, DuplicateEntitiesCommand, MoveCommand, RotateCommand, ScaleCommand
from core.commands.history import CommandHistory
from core.commands.multileader import (
    AddMultileaderCommand,
    ApplyMultileaderStyleCommand,
    DefineMultileaderStyleCommand,
    DeleteMultileaderStyleCommand,
    EditMultileaderTextCommand,
    MoveMultileaderGripCommand,
    RescaleAnnotativeCommand,
    SetMultileaderPropertiesCommand,
)
from core.commands.text import SetEntityColorCommand
from core.dxf_document import DXFDocument
from core.exceptions import MultileaderError
from core.multileader import (
    ARROW_BLOCK_NAMES,
    ARROWHEADS,
    MULTILEADER_APPID,
    MultileaderSpec,
    MultileaderStyle,
    connection_side,
    constrain_angle,
    mtext_content,
    text_alignment,
)
from core.project import ProjectState, load_project, save_project


def _spec(**changes) -> MultileaderSpec:
    values = {
        "tip": (1.0, 2.0),
        "landing": (5.0, 4.0),
        "text_position": (8.0, 4.0),
        "text": "Boundary marker",
        "height": 0.6,
        "layer": "ANNOTATIONS",
    }
    values.update(changes)
    return MultileaderSpec(**values)


def _add(doc: DXFDocument, **changes) -> str:
    command = AddMultileaderCommand(_spec(**changes))
    command.execute(doc)
    return command.handle


def _connection(entity):
    leader = entity.context.leaders[0]
    point = leader.last_leader_point
    if entity.dxf.has_dogleg:
        point = point + leader.dogleg_vector * leader.dogleg_length
    return point.x, point.y


def test_multileader_is_one_native_entity() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)

    entity = doc.get_entity(handle)
    assert doc.entity_count() == 1
    assert entity.dxftype() == "MULTILEADER"
    assert entity.dxf.layer == "ANNOTATIONS"
    assert doc.multileader_text(handle) == "Boundary marker"
    assert doc.multileader_grips(handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]
    leader = entity.context.leaders[0]
    assert leader.lines[0].vertices[0].isclose((1.0, 2.0, 0.0))
    assert (leader.last_leader_point.x, leader.last_leader_point.y) == pytest.approx((5.0, 4.0))
    assert _connection(entity) == pytest.approx((8.0, 4.0))
    assert sorted(v.dxftype() for v in entity.virtual_entities()) == ["INSERT", "LINE", "LINE", "MTEXT"]


def test_landing_point_pulls_text_onto_its_line() -> None:
    spec = _spec(text_position=(8.0, 9.0)).normalized()

    assert spec.text_position == (8.0, 4.0)


def test_attachment_follows_text_side_automatically() -> None:
    right = _spec().normalized()
    left = _spec(text_position=(1.0, 4.0)).normalized()

    assert connection_side(right) == "left"
    assert text_alignment(right) == "left"
    assert connection_side(left) == "right"
    assert text_alignment(left) == "right"


def test_text_grip_move_flips_attachment() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)

    MoveMultileaderGripCommand(handle, "text", (0.0, 4.0)).execute(doc)

    entity = doc.get_entity(handle)
    assert entity.context.mtext.alignment == 3
    assert _connection(entity) == pytest.approx((0.0, 4.0))


def test_landing_length_derives_landing_from_text_side() -> None:
    left = _spec(landing_length=2.0).normalized()
    right = _spec(landing_length=2.0, text_position=(-4.0, 4.0)).normalized()

    assert left.landing == pytest.approx((6.0, 4.0))
    assert right.landing == pytest.approx((-2.0, 4.0))


def test_undo_redo_and_delete() -> None:
    doc = DXFDocument.new()
    history = CommandHistory()
    command = AddMultileaderCommand(_spec())
    history.execute(command, doc)

    assert history.undo(doc)
    assert doc.entity_count() == 0
    assert history.redo(doc)
    assert doc.entity_count() == 1

    history.execute(DeleteEntityCommand([command.handle]), doc)
    assert doc.entity_count() == 0
    assert history.undo(doc)
    assert doc.entity_count() == 1


def test_move_rotate_scale_update_grips_and_undo() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)
    history = CommandHistory()

    history.execute(MoveCommand([handle], 2.0, -3.0), doc)
    assert doc.multileader_grips(handle) == [(3.0, -1.0), (7.0, 1.0), (10.0, 1.0)]
    assert history.undo(doc)
    assert doc.multileader_grips(handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]

    RotateCommand([handle], 90.0, (0.0, 0.0)).execute(doc)
    assert doc.multileader_grips(handle) == [
        pytest.approx((-2.0, 1.0)),
        pytest.approx((-4.0, 5.0)),
        pytest.approx((-4.0, 8.0)),
    ]
    assert doc.get_entity(handle).context.mtext.rotation == pytest.approx(math.pi / 2)

    ScaleCommand([handle], 2.0, (0.0, 0.0)).execute(doc)
    assert doc.multileader_grips(handle) == [
        pytest.approx((-4.0, 2.0)),
        pytest.approx((-8.0, 10.0)),
        pytest.approx((-8.0, 16.0)),
    ]
    assert doc.multileader_spec(handle).height == pytest.approx(1.2)


def test_duplicate_gets_its_own_identity_and_position() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)
    duplicate = DuplicateEntitiesCommand([handle], 10.0, 0.0)

    duplicate.execute(doc)

    (copy,) = duplicate.new_handles
    assert doc.entity_count() == 2
    assert doc.multileader_spec(copy).identifier != doc.multileader_spec(handle).identifier
    assert doc.multileader_grips(handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]
    assert doc.multileader_grips(copy) == [(11.0, 2.0), (15.0, 4.0), (18.0, 4.0)]
    MoveCommand([copy], 0.0, 5.0).execute(doc)
    assert doc.multileader_grips(copy) == [(11.0, 7.0), (15.0, 9.0), (18.0, 9.0)]
    assert _connection(doc.get_entity(copy)) == pytest.approx((18.0, 9.0))


def test_entity_color_drives_by_block_parts() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)
    edit = SetEntityColorCommand(handle, (20, 30, 40))

    edit.execute(doc)

    entity = doc.get_entity(handle)
    assert doc.get_entity_color(handle) == (20, 30, 40)
    assert entity.dxf.leader_line_color == -1056964608
    edit.undo(doc)
    assert doc.get_entity_color(handle) == doc.get_layer_color("ANNOTATIONS")


def test_dxf_and_project_round_trip(tmp_path) -> None:
    doc = DXFDocument.new()
    handle = _add(doc, line_type="spline", arrowhead="open", text="Two\nlines")
    content = doc.to_text()

    reopened = DXFDocument.from_text(content)
    assert reopened.get_entity(handle).dxftype() == "MULTILEADER"
    assert reopened.multileader_spec(handle).line_type == "spline"
    assert reopened.multileader_text(handle) == "Two\nlines"

    path = tmp_path / "leader.gsgproj"
    save_project(path, ProjectState(name="Leader", dxf_content=content))
    project_doc = DXFDocument.from_text(load_project(path).dxf_content)
    assert project_doc.multileader_grips(handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]


@pytest.mark.parametrize("arrowhead", ARROWHEADS)
def test_every_arrowhead_builds(arrowhead: str) -> None:
    doc = DXFDocument.new()
    handle = _add(doc, arrowhead=arrowhead)

    entity = doc.get_entity(handle)
    name = ARROW_BLOCK_NAMES[arrowhead]
    if name:
        assert entity.dxf.arrow_head_handle == doc.drawing.blocks.get(ARROWS.block_name(name)).block_record_handle
    else:
        assert not entity.dxf.hasattr("arrow_head_handle")
    assert list(entity.virtual_entities())


def test_block_arrowhead_uses_the_block() -> None:
    doc = DXFDocument.new()
    block = doc.drawing.blocks.new("MARK")
    block.add_circle((0, 0), 1.0)
    handle = _add(doc, arrow_block="MARK")

    assert doc.get_entity(handle).dxf.arrow_head_handle == block.block_record_handle


def test_leader_appearance_is_written() -> None:
    doc = DXFDocument.new()
    handle = _add(doc, arrow_size=0.5, leader_color=(255, 0, 0), leader_lineweight=35, scale=2.0)

    entity = doc.get_entity(handle)
    assert entity.dxf.arrow_head_size == pytest.approx(1.0)
    assert entity.dxf.leader_lineweight == 35
    assert entity.dxf.leader_line_color != -1056964608
    assert entity.context.char_height == pytest.approx(1.2)


def test_mtext_formatting() -> None:
    spec = _spec(text="a{b}\nc", bold=True, underline=True, font="arial").normalized()

    assert mtext_content(spec) == "{\\fArial|b1|i0|c0|p0;\\La\\{b\\}\\Pc\\l}"
    assert mtext_content(_spec(bold=True, font="romans").normalized()) == "Boundary marker"


def test_frame_background_spacing_and_alignment() -> None:
    doc = DXFDocument.new()
    handle = _add(doc, text_frame=True, background=True, background_scale=2.0, line_spacing=1.5, alignment="center")

    entity = doc.get_entity(handle)
    mtext = entity.context.mtext
    assert entity.dxf.has_text_frame == 1
    assert mtext.has_bg_fill == 1
    assert mtext.bg_scale_factor == pytest.approx(2.0)
    assert mtext.line_spacing_factor == pytest.approx(1.5)
    assert mtext.alignment == 2
    assert _connection(entity) == pytest.approx((8.0, 4.0))


def test_connection_types_and_vertical_direction() -> None:
    doc = DXFDocument.new()
    horizontal = _add(doc, left_connection="bottom_of_bottom_line_underline")
    vertical = _add(doc, direction="vertical", text_position=(1.0, 6.0), top_connection="center_overline")

    assert doc.get_entity(horizontal).context.left_attachment == 5
    entity = doc.get_entity(vertical)
    assert entity.dxf.text_attachment_direction == 1
    assert connection_side(doc.multileader_spec(vertical)) == "bottom"
    assert doc.multileader_grips(vertical) == [(1.0, 2.0), (1.0, 6.0)]
    assert _connection(entity) == pytest.approx((1.0, 6.0))


def test_constrain_angle_snaps_direction_and_keeps_length() -> None:
    snapped = constrain_angle((0.0, 0.0), (10.0, 1.0), 45)

    assert snapped == pytest.approx((math.hypot(10.0, 1.0), 0.0))
    assert constrain_angle((0.0, 0.0), (3.0, 4.0), 0) == (3.0, 4.0)


def test_empty_text_has_no_content() -> None:
    doc = DXFDocument.new()
    handle = _add(doc, text="", landing_enabled=False)

    entity = doc.get_entity(handle)
    assert entity.dxf.content_type == 0
    assert "MTEXT" not in [v.dxftype() for v in entity.virtual_entities()]
    assert DXFDocument.from_text(doc.to_text()).multileader_text(handle) == ""


def test_style_is_native_and_rebuilds_existing_leaders() -> None:
    doc = DXFDocument.new()
    history = CommandHistory()
    add = AddMultileaderCommand(_spec(style_name="Survey"))
    history.execute(add, doc)
    style = MultileaderStyle(name="Survey", arrowhead="dot", height=1.5, landing_length=1.0, text_frame=True)

    history.execute(DefineMultileaderStyleCommand(style), doc)

    native = doc.drawing.mleader_styles.get("Survey")
    assert native.dxf.char_height == pytest.approx(1.5)
    assert native.dxf.has_text_frame == 1
    assert doc.multileader_styles()["Survey"] == style.normalized()
    spec = doc.multileader_spec(add.handle)
    assert (spec.arrowhead, spec.height, spec.landing_length, spec.text_frame) == ("dot", 1.5, 1.0, True)
    assert doc.get_entity(add.handle).dxf.style_handle == native.dxf.handle

    assert history.undo(doc)
    assert "Survey" not in doc.multileader_styles()
    assert doc.multileader_spec(add.handle).arrowhead == "closed"
    assert history.redo(doc)
    assert doc.multileader_spec(add.handle).arrowhead == "dot"


def test_styles_survive_dxf_round_trip(tmp_path) -> None:
    doc = DXFDocument.new()
    doc.set_multileader_styles({"A": MultileaderStyle(name="A", annotative=True, scale=2.0, first_angle=15)})
    path = tmp_path / "styles.dxf"
    doc.save(str(path))

    loaded = DXFDocument.load(str(path)).multileader_styles()["A"]
    assert loaded.annotative is True
    assert loaded.first_angle == 15
    assert "Standard" in DXFDocument.load(str(path)).multileader_styles()


def test_delete_style_refuses_standard_and_styles_in_use() -> None:
    doc = DXFDocument.new()
    doc.set_multileader_styles({"Used": MultileaderStyle(name="Used"), "Free": MultileaderStyle(name="Free")})
    _add(doc, style_name="Used")

    with pytest.raises(MultileaderError):
        DeleteMultileaderStyleCommand("Standard").execute(doc)
    with pytest.raises(MultileaderError):
        DeleteMultileaderStyleCommand("Used").execute(doc)
    command = DeleteMultileaderStyleCommand("Free")
    command.execute(doc)
    assert "Free" not in doc.multileader_styles()
    command.undo(doc)
    assert "Free" in doc.multileader_styles()


def test_apply_style_to_selected_leader() -> None:
    doc = DXFDocument.new()
    doc.set_multileader_styles({"Big": MultileaderStyle(name="Big", height=2.0, arrowhead="oblique")})
    handle = _add(doc)

    command = ApplyMultileaderStyleCommand("Big", handles=[handle])
    command.execute(doc)

    assert doc.multileader_spec(handle).style_name == "Big"
    assert doc.multileader_spec(handle).arrowhead == "oblique"
    command.undo(doc)
    assert doc.multileader_spec(handle).style_name == ""


def test_annotative_rescale_only_touches_annotative_styles() -> None:
    doc = DXFDocument.new()
    doc.set_multileader_styles(
        {
            "Anno": MultileaderStyle(name="Anno", annotative=True),
            "Fixed": MultileaderStyle(name="Fixed"),
        }
    )
    anno = _add(doc, style_name="Anno")
    fixed = _add(doc, style_name="Fixed")
    command = RescaleAnnotativeCommand(2.0)

    command.execute(doc)

    assert doc.multileader_spec(anno).scale == 2.0
    assert doc.multileader_spec(fixed).scale == 1.0
    command.undo(doc)
    assert doc.multileader_spec(anno).scale == 1.0


def test_grip_text_and_property_edits_keep_handle_and_undo() -> None:
    doc = DXFDocument.new()
    history = CommandHistory()
    handle = _add(doc)

    history.execute(MoveMultileaderGripCommand(handle, "tip", (0.0, 0.0)), doc)
    history.execute(EditMultileaderTextCommand(handle, "New"), doc)
    history.execute(SetMultileaderPropertiesCommand([handle], arrowhead="integral", text_frame=True), doc)

    spec = doc.multileader_spec(handle)
    assert (spec.tip, spec.text, spec.arrowhead, spec.text_frame) == ((0.0, 0.0), "New", "integral", True)
    assert doc.multileader_text(handle) == "New"
    assert history.undo(doc) and history.undo(doc) and history.undo(doc)
    spec = doc.multileader_spec(handle)
    assert (spec.tip, spec.text, spec.arrowhead) == ((1.0, 2.0), "Boundary marker", "closed")


def test_foreign_multileader_without_metadata_is_editable() -> None:
    doc = DXFDocument.new()
    handle = _add(doc)
    doc.get_entity(handle).discard_xdata(MULTILEADER_APPID)

    spec = doc.multileader_spec(handle)

    assert spec.tip == pytest.approx((1.0, 2.0))
    assert spec.landing == pytest.approx((5.0, 4.0))
    assert spec.text_position == pytest.approx((8.0, 4.0))
    assert spec.text == "Boundary marker"
    MoveCommand([handle], 1.0, 0.0).execute(doc)
    assert doc.multileader_grips(handle)[0] == pytest.approx((2.0, 2.0))


def _legacy_drawing() -> str:
    doc = DXFDocument.new()
    drawing = doc.drawing
    drawing.appids.add(MULTILEADER_APPID)
    payload = {
        "tip": [1.0, 2.0],
        "landing": [5.0, 4.0],
        "text_position": [8.18, 4.0],
        "text": "Old",
        "height": 0.6,
        "line_type": "straight",
        "arrowhead": "closed",
        "attachment": "left",
        "landing_enabled": True,
        "gap": 0.18,
        "layer": "ANNOTATIONS",
        "identifier": "legacy-id",
        "landing_length": 0.0,
        "scale": 1.0,
        "style_name": "Old",
    }
    msp = drawing.modelspace()
    for role, entity in (
        ("leader", msp.add_lwpolyline([(1, 2), (5, 4), (8, 4)])),
        ("arrow", msp.add_solid([(1, 2), (1.5, 2.3), (1.4, 2.5)])),
        ("text", msp.add_text("Old", dxfattribs={"insert": (8.18, 4.0)})),
    ):
        entity.set_xdata(MULTILEADER_APPID, [(1000, "1"), (1000, "legacy-id"), (1000, role), (1000, json.dumps(payload))])
    drawing.rootdict.add_dict_var(
        "GSG_MLEADER_STYLES", json.dumps([{"name": "Old", "arrowhead": "dot", "height": 0.6, "annotative": True}])
    )
    return doc.to_text()


def test_legacy_groups_and_styles_migrate_on_open() -> None:
    doc = DXFDocument.from_text(_legacy_drawing())

    (entity,) = list(doc.modelspace)
    assert entity.dxftype() == "MULTILEADER"
    spec = doc.multileader_spec(entity.dxf.handle)
    assert spec.identifier == "legacy-id"
    assert spec.text == "Old"
    assert spec.text_position == pytest.approx((8.0, 4.0))
    assert spec.left_connection == "bottom_of_top_line"
    assert doc.multileader_styles()["Old"].annotative is True
    assert doc.drawing.rootdict.get("GSG_MLEADER_STYLES") is None


def _foreign_multileader(doc: DXFDocument) -> str:
    from ezdxf.math import Vec2
    from ezdxf.render.mleader import ConnectionSide, TextAlignment

    drawing = doc.drawing
    drawing.mleader_styles.duplicate_entry("Standard", "Imported")
    builder = doc.modelspace.add_multileader_mtext("Imported")
    builder.set_content(r"{\fArial|b1;Imported}\Pnote", color=3, char_height=0.5, alignment=TextAlignment.left)
    builder.set_arrow_properties(name=ARROWS.integral, size=0.4)
    builder.set_connection_properties(landing_gap=0.1, dogleg_length=1.0)
    builder.add_leader_line(ConnectionSide.left, [Vec2(0.0, 0.0), Vec2(2.0, 1.0)])
    builder.add_leader_line(ConnectionSide.left, [Vec2(0.0, 3.0)])
    builder.build(insert=Vec2(5.0, 2.0))
    return builder.multileader.dxf.handle


def _native_state(entity):
    attribs = {key: value for key, value in entity.dxf.all_existing_dxf_attribs().items() if key != "handle"}
    leaders = [
        [[tuple(round(c, 9) for c in vertex) for vertex in line.vertices] for line in leader.lines]
        for leader in entity.context.leaders
    ]
    mtext = entity.context.mtext
    return attribs, leaders, mtext.default_content, tuple(round(c, 9) for c in mtext.insert)


@pytest.mark.parametrize(
    "transform",
    [
        lambda handle: MoveCommand([handle], 3.0, 1.0),
        lambda handle: RotateCommand([handle], 30.0, (0.0, 0.0)),
        lambda handle: ScaleCommand([handle], 2.0, (0.0, 0.0)),
    ],
)
def test_transforming_imported_multileader_keeps_its_contents(transform) -> None:
    doc = DXFDocument.new()
    handle = _foreign_multileader(doc)
    entity = doc.get_entity(handle)
    before = _native_state(entity)
    command = transform(handle)

    command.execute(doc)

    assert len(entity.context.leaders[0].lines) == 2
    assert entity.context.mtext.default_content == before[2]
    assert entity.dxf.arrow_head_handle == before[0]["arrow_head_handle"]
    assert entity.dxf.style_handle == before[0]["style_handle"]
    assert entity.dxf.text_color == before[0]["text_color"]
    assert not entity.has_xdata(MULTILEADER_APPID)
    command.undo(doc)
    after = _native_state(entity)
    assert after[1:] == before[1:]
    assert after[0].keys() == before[0].keys()


def test_duplicating_imported_multileader_keeps_its_contents() -> None:
    doc = DXFDocument.new()
    handle = _foreign_multileader(doc)

    duplicate = DuplicateEntitiesCommand([handle], 10.0, 0.0)
    duplicate.execute(doc)

    (copy,) = duplicate.new_handles
    entity = doc.get_entity(copy)
    assert len(entity.context.leaders[0].lines) == 2
    assert entity.context.mtext.default_content == doc.get_entity(handle).context.mtext.default_content
    assert entity.context.leaders[0].lines[0].vertices[0].isclose((10.0, 0.0, 0.0))


def test_undoing_an_edit_of_imported_multileader_restores_it_exactly() -> None:
    doc = DXFDocument.new()
    handle = _foreign_multileader(doc)
    entity = doc.get_entity(handle)
    before = _native_state(entity)
    history = CommandHistory()

    history.execute(EditMultileaderTextCommand(handle, "Changed"), doc)
    assert doc.multileader_text(handle) == "Changed"
    assert history.undo(doc)

    assert _native_state(entity) == before
    assert not entity.has_xdata(MULTILEADER_APPID)
    assert history.redo(doc)
    assert doc.multileader_text(handle) == "Changed"


def test_style_referenced_only_by_imported_multileader_is_in_use() -> None:
    doc = DXFDocument.new()
    handle = _foreign_multileader(doc)
    entity = doc.get_entity(handle)
    before = _native_state(entity)

    assert doc.multileader_style_in_use("Imported")
    with pytest.raises(MultileaderError):
        DeleteMultileaderStyleCommand("Imported").execute(doc)
    assert "Imported" in doc.multileader_styles()

    DefineMultileaderStyleCommand(MultileaderStyle(name="Imported", arrowhead="dot")).execute(doc)
    assert _native_state(entity)[1:] == before[1:]
    assert not entity.has_xdata(MULTILEADER_APPID)


def test_imported_style_is_loaded_for_drawing() -> None:
    from core.multileader import apply_style

    doc = DXFDocument.new()
    native = doc.drawing.mleader_styles.duplicate_entry("Standard", "Survey")
    native.dxf.arrow_head_handle = ARROWS.arrow_handle(doc.drawing.blocks, ARROWS.integral)
    native.dxf.arrow_head_size = 0.4
    native.dxf.char_height = 1.25
    native.dxf.leader_line_color = -1023410175
    native.dxf.text_attachment_direction = 1
    native.dxf.text_top_attachment_type = 10
    native.dxf.text_left_attachment_type = 2
    native.dxf.has_text_frame = 1
    native.dxf.first_segment_angle_constraint = math.radians(45)

    style = doc.drawing_multileader_style("Survey")

    assert style is not None
    assert (style.arrowhead, style.arrow_size, style.height) == ("integral", 0.4, 1.25)
    assert style.leader_color == (255, 0, 0)
    assert (style.direction, style.top_connection, style.left_connection) == ("vertical", "center_overline", "middle_of_text")
    assert style.text_frame is True
    assert style.first_angle == 45
    assert doc.drawing_multileader_style("Standard") is None

    handle = doc.add_multileader(apply_style(_spec(), style))
    entity = doc.get_entity(handle)
    assert entity.dxf.style_handle == native.dxf.handle
    assert entity.dxf.arrow_head_handle == native.dxf.arrow_head_handle
