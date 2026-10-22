from __future__ import annotations

import math

import pytest

from core.commands.history import CommandHistory
from core.commands.properties import SetEntityPropertyCommand
from core.dxf_document import DXFDocument
from core.entity_properties import (
    BYLAYER_COLOR,
    TRANSPARENCY_BYBLOCK,
    TRANSPARENCY_BYLAYER,
    VARIES,
    ColorValue,
    describe,
    selection_types,
)
from core.exceptions import InvalidPropertyValueError


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


def _rows(doc: DXFDocument, *handles: str) -> dict:
    return {row.key: row for row in describe(doc.entities_for(handles))}


def test_line_shows_general_and_geometry_properties(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (3.0, 4.0))
    rows = _rows(doc, handle)
    assert rows["layer"].value == "0"
    assert rows["color"].value == BYLAYER_COLOR
    assert rows["linetype"].value == "ByLayer"
    assert rows["ltscale"].value == 1.0
    assert rows["transparency"].value == TRANSPARENCY_BYLAYER
    assert rows["end_x"].value == 3.0 and rows["end_x"].editable
    assert rows["length"].value == pytest.approx(5.0) and not rows["length"].editable
    assert rows["angle"].value == pytest.approx(math.degrees(math.atan2(4, 3)))
    assert not rows["angle"].editable


def test_circle_and_arc_derived_values(doc: DXFDocument) -> None:
    circle = doc.add_circle((1.0, 1.0), 2.0)
    rows = _rows(doc, circle)
    assert rows["diameter"].value == pytest.approx(4.0) and rows["diameter"].editable
    assert rows["area"].value == pytest.approx(math.pi * 4.0) and not rows["area"].editable
    arc = doc.modelspace.add_arc((0, 0), 2.0, 350.0, 80.0).dxf.handle
    rows = _rows(doc, arc)
    assert rows["total_angle"].value == pytest.approx(90.0)
    assert rows["arc_length"].value == pytest.approx(math.pi)


def test_closed_polyline_length_and_area(doc: DXFDocument) -> None:
    handle = doc.add_lwpolyline([(0, 0), (4, 0), (4, 3), (0, 3)], closed=True)
    rows = _rows(doc, handle)
    assert rows["closed"].value is True
    assert rows["length"].value == pytest.approx(14.0)
    assert rows["area"].value == pytest.approx(12.0)


def test_polyline_with_bulges_measures_arcs_exactly(doc: DXFDocument) -> None:
    circle = doc.modelspace.add_lwpolyline([(0, 0, 1.0), (2, 0, 1.0)], format="xyb", close=True).dxf.handle
    rows = _rows(doc, circle)
    assert rows["length"].value == pytest.approx(2 * math.pi)
    assert rows["area"].value == pytest.approx(math.pi)
    half_disc = doc.modelspace.add_lwpolyline([(0, 0, -1.0), (2, 0, 0.0)], format="xyb").dxf.handle
    rows = _rows(doc, half_disc)
    assert rows["length"].value == pytest.approx(math.pi)
    assert rows["area"].value == pytest.approx(math.pi / 2)
    old_style = doc.modelspace.add_polyline2d([(0, 0), (3, 0), (3, 4)], close=True).dxf.handle
    rows = _rows(doc, old_style)
    assert rows["length"].value == pytest.approx(12.0)
    assert rows["area"].value == pytest.approx(6.0)


def test_text_and_insert_properties(doc: DXFDocument) -> None:
    text = doc.modelspace.add_text("Abc", dxfattribs={"height": 2.5, "insert": (1, 2)}).dxf.handle
    rows = _rows(doc, text)
    assert rows["contents"].value == "Abc"
    assert rows["height"].value == 2.5
    assert (rows["position_x"].value, rows["position_y"].value) == (1.0, 2.0)
    doc.drawing.blocks.new("B")
    insert = doc.modelspace.add_blockref("B", (5, 6), dxfattribs={"rotation": 30}).dxf.handle
    rows = _rows(doc, insert)
    assert rows["name"].value == "B" and not rows["name"].editable
    assert rows["rotation"].value == pytest.approx(30.0)


def test_mixed_selection_shares_general_rows_and_marks_differences(doc: DXFDocument) -> None:
    doc.add_layer("A")
    line = doc.add_line((0, 0), (1, 0), layer="A")
    circle = doc.add_circle((0, 0), 1.0, layer="0")
    rows = _rows(doc, line, circle)
    assert set(rows) == {"layer", "color", "linetype", "ltscale", "lineweight", "transparency"}
    assert rows["layer"].value is VARIES
    assert rows["color"].value == BYLAYER_COLOR
    assert selection_types(doc.entities_for([line, circle, line])) == [("LINE", 2), ("CIRCLE", 1)]


def test_two_lines_share_geometry_rows(doc: DXFDocument) -> None:
    a = doc.add_line((0, 0), (1, 0))
    b = doc.add_line((0, 0), (2, 0))
    rows = _rows(doc, a, b)
    assert rows["start_x"].value == 0.0
    assert rows["end_x"].value is VARIES


@pytest.mark.parametrize(
    "key, value",
    [
        ("color", ColorValue(1)),
        ("color", ColorValue(7, (10, 20, 30))),
        ("linetype", "DASHED"),
        ("lineweight", 50),
        ("transparency", 40),
        ("transparency", TRANSPARENCY_BYBLOCK),
        ("ltscale", 2.5),
        ("end_x", 9.0),
    ],
)
def test_set_property_on_many_lines_and_undo(doc: DXFDocument, key: str, value) -> None:
    doc.drawing.linetypes.add("DASHED", pattern=[0.5, 0.25, -0.25])
    handles = [doc.add_line((0, 0), (1, 1)), doc.add_line((2, 2), (3, 3))]
    before = [doc.get_entity_property(handle, key) for handle in handles]
    history = CommandHistory()
    history.execute(SetEntityPropertyCommand(handles, key, value), doc)
    assert [doc.get_entity_property(handle, key) for handle in handles] == [value, value]
    history.undo(doc)
    assert [doc.get_entity_property(handle, key) for handle in handles] == before


def test_set_color_back_to_bylayer_drops_true_color(doc: DXFDocument) -> None:
    handle = doc.add_line((0, 0), (1, 1))
    doc.set_entity_property(handle, "color", ColorValue(7, (10, 20, 30)))
    doc.set_entity_property(handle, "color", BYLAYER_COLOR)
    assert doc.get_entity_property(handle, "color") == BYLAYER_COLOR


def test_set_layer_creates_missing_layer(doc: DXFDocument) -> None:
    handle = doc.add_line((0, 0), (1, 1))
    SetEntityPropertyCommand([handle], "layer", "NOWA").execute(doc)
    assert doc.get_entity_property(handle, "layer") == "NOWA"
    assert "NOWA" in doc.layers


def test_geometry_edits_and_undo(doc: DXFDocument) -> None:
    circle = doc.add_circle((0, 0), 1.0)
    polyline = doc.add_lwpolyline([(0, 0), (1, 0), (1, 1)])
    mtext = doc.modelspace.add_mtext("stary").dxf.handle
    commands = [
        SetEntityPropertyCommand([circle], "diameter", 10.0),
        SetEntityPropertyCommand([polyline], "closed", True),
        SetEntityPropertyCommand([mtext], "contents", "nowy"),
    ]
    for command in commands:
        command.execute(doc)
    assert doc.get_entity_property(circle, "radius") == 5.0
    assert doc.get_entity_property(polyline, "closed") is True
    assert doc.get_entity_property(mtext, "contents") == "nowy"
    for command in reversed(commands):
        command.undo(doc)
    assert doc.get_entity_property(circle, "radius") == 1.0
    assert doc.get_entity_property(polyline, "closed") is False
    assert doc.get_entity_property(mtext, "contents") == "stary"


def test_moving_aligned_text_moves_both_anchor_points(doc: DXFDocument) -> None:
    text = doc.modelspace.add_text("A", dxfattribs={"halign": 1, "insert": (0, 0), "align_point": (5, 5)})
    doc.set_entity_property(text.dxf.handle, "position_x", 8.0)
    assert text.dxf.align_point.x == 8.0
    assert text.dxf.insert.x == 3.0


def test_invalid_value_rolls_back_every_entity(doc: DXFDocument) -> None:
    a = doc.add_circle((0, 0), 1.0)
    b = doc.add_circle((0, 0), 2.0)
    with pytest.raises(InvalidPropertyValueError):
        SetEntityPropertyCommand([a, b], "radius", 0.0).execute(doc)
    assert [doc.get_entity_property(h, "radius") for h in (a, b)] == [1.0, 2.0]


def test_read_only_property_cannot_be_set(doc: DXFDocument) -> None:
    handle = doc.add_line((0, 0), (1, 1))
    with pytest.raises(KeyError):
        doc.set_entity_property(handle, "length", 3.0)
