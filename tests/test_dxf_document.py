"""Tests for core.dxf_document.DXFDocument."""
from __future__ import annotations

import pytest

from core.dxf_document import DXFDocument


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


def test_new_document_is_empty(doc: DXFDocument) -> None:
    assert doc.entity_count() == 0
    assert doc.layer_count() >= 1  # ezdxf always ships a default "0" layer


def test_add_point_returns_handle_and_increments_count(doc: DXFDocument) -> None:
    handle = doc.add_point((1.0, 2.0))
    assert isinstance(handle, str) and handle
    assert doc.entity_count() == 1
    entity = doc.get_entity(handle)
    assert entity is not None
    assert entity.dxftype() == "POINT"
    assert entity.dxf.layer == "0"


def test_add_line_creates_line_entity_with_given_layer(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (10.0, 10.0), layer="SURVEY")
    entity = doc.get_entity(handle)
    assert entity.dxftype() == "LINE"
    assert entity.dxf.layer == "SURVEY"
    assert tuple(entity.dxf.start)[:2] == (0.0, 0.0)
    assert tuple(entity.dxf.end)[:2] == (10.0, 10.0)


def test_add_circle_creates_circle_entity(doc: DXFDocument) -> None:
    handle = doc.add_circle((5.0, 5.0), radius=2.5)
    entity = doc.get_entity(handle)
    assert entity.dxftype() == "CIRCLE"
    assert entity.dxf.radius == 2.5


def test_add_point_accepts_a_3d_location(doc: DXFDocument) -> None:
    handle = doc.add_point((1.0, 2.0, 3.0))
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.location) == (1.0, 2.0, 3.0)


def test_add_text_creates_text_entity_with_placement_and_rotation(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (1.0, 2.0, 3.0), height=0.6, layer="LABELS", rotation=15.0)
    entity = doc.get_entity(handle)
    assert entity.dxftype() == "TEXT"
    assert entity.dxf.text == "42"
    assert tuple(entity.dxf.insert) == (1.0, 2.0, 3.0)
    assert entity.dxf.height == 0.6
    assert entity.dxf.rotation == 15.0
    assert entity.dxf.layer == "LABELS"


def test_add_lwpolyline_creates_2d_polyline_through_points(doc: DXFDocument) -> None:
    handle = doc.add_lwpolyline([(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)], layer="SURVEY")
    entity = doc.get_entity(handle)
    assert entity.dxftype() == "LWPOLYLINE"
    assert entity.dxf.layer == "SURVEY"
    assert entity.closed is False
    assert [pt[:2] for pt in entity.get_points("xy")] == [(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)]


def test_add_lwpolyline_closed(doc: DXFDocument) -> None:
    handle = doc.add_lwpolyline([(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)], closed=True)
    entity = doc.get_entity(handle)
    assert entity.closed is True


def test_add_polyline3d_creates_3d_polyline_through_points(doc: DXFDocument) -> None:
    points = [(0.0, 0.0, 1.0), (1.0, 1.0, 2.0), (2.0, 0.0, 3.0)]
    handle = doc.add_polyline3d(points, layer="SURVEY")
    entity = doc.get_entity(handle)
    assert entity.dxftype() == "POLYLINE"
    assert entity.dxf.layer == "SURVEY"
    assert [tuple(v) for v in entity.points()] == points


def test_ensure_layer_creates_missing_layer_once(doc: DXFDocument) -> None:
    assert "SURVEY" not in doc.layers
    doc.ensure_layer("SURVEY")
    assert "SURVEY" in doc.layers
    doc.ensure_layer("SURVEY")  # must not raise on a second call
    assert "SURVEY" in doc.layers


def test_add_point_auto_creates_its_layer(doc: DXFDocument) -> None:
    assert "SURVEY" not in doc.layers
    doc.add_point((0.0, 0.0), layer="SURVEY")
    assert "SURVEY" in doc.layers


def test_unlink_entity_removes_it_from_modelspace_but_keeps_it_in_the_database(doc: DXFDocument) -> None:
    handle = doc.add_point((0.0, 0.0))
    entity = doc.unlink_entity(handle)
    assert doc.entity_count() == 0
    assert doc.get_entity(handle) is not None  # still alive in the entitydb
    assert entity.dxf.handle == handle


def test_unlink_entity_raises_for_unknown_handle(doc: DXFDocument) -> None:
    with pytest.raises(KeyError):
        doc.unlink_entity("does-not-exist")


def test_restore_entity_puts_it_back_in_modelspace(doc: DXFDocument) -> None:
    handle = doc.add_point((3.0, 4.0))
    entity = doc.unlink_entity(handle)
    doc.restore_entity(entity)
    assert doc.entity_count() == 1
    assert doc.get_entity(handle) is entity
