"""Tests for core.dxf_document.DXFDocument."""
from __future__ import annotations

import ezdxf
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


def test_translate_entity_moves_it_by_the_given_vector(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (1.0, 1.0))
    doc.translate_entity(handle, 5.0, -2.0)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == (5.0, -2.0)
    assert tuple(entity.dxf.end)[:2] == (6.0, -1.0)


def test_translate_entity_raises_for_unknown_handle(doc: DXFDocument) -> None:
    with pytest.raises(KeyError):
        doc.translate_entity("does-not-exist", 1.0, 1.0)


def test_add_layer_creates_it_with_the_given_color(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(200, 50, 50))
    assert "SURVEY" in doc.layers
    assert doc.get_layer_color("SURVEY") == (200, 50, 50)


def test_add_layer_is_idempotent(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.add_layer("SURVEY")  # must not raise on a second call
    assert "SURVEY" in doc.layers


def test_remove_layer_deletes_the_table_entry(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.remove_layer("SURVEY")
    assert "SURVEY" not in doc.layers


def test_remove_layer_refuses_to_delete_layer_zero(doc: DXFDocument) -> None:
    with pytest.raises(ValueError):
        doc.remove_layer("0")


def test_remove_layer_resets_active_layer_to_zero_if_it_was_active(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.set_active_layer("SURVEY")
    doc.remove_layer("SURVEY")
    assert doc.active_layer == "0"


def test_set_layer_color_round_trips(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.set_layer_color("SURVEY", (10, 20, 30))
    assert doc.get_layer_color("SURVEY") == (10, 20, 30)


def test_layer_visibility_defaults_to_visible_and_toggles(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    assert doc.is_layer_visible("SURVEY") is True
    doc.set_layer_visible("SURVEY", False)
    assert doc.is_layer_visible("SURVEY") is False
    doc.set_layer_visible("SURVEY", True)
    assert doc.is_layer_visible("SURVEY") is True


def test_active_layer_defaults_to_zero_and_is_settable(doc: DXFDocument) -> None:
    assert doc.active_layer == "0"
    doc.set_active_layer("SURVEY")
    assert doc.active_layer == "SURVEY"


def test_set_active_layer_creates_the_layer_if_missing(doc: DXFDocument) -> None:
    assert "SURVEY" not in doc.layers
    doc.set_active_layer("SURVEY")
    assert "SURVEY" in doc.layers


def test_iter_layers_reports_name_color_visibility_active_and_counts(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(1, 2, 3))
    doc.add_point((0.0, 0.0), layer="SURVEY")
    doc.add_point((1.0, 1.0), layer="SURVEY")
    doc.set_active_layer("SURVEY")

    infos = {info.name: info for info in doc.iter_layers()}
    assert infos["0"].is_active is False
    survey = infos["SURVEY"]
    assert survey.rgb == (1, 2, 3)
    assert survey.visible is True
    assert survey.is_active is True
    assert survey.entity_count == 2


def test_iter_layers_lists_layer_zero_first(doc: DXFDocument) -> None:
    doc.add_layer("AAA")
    names = [info.name for info in doc.iter_layers()]
    assert names[0] == "0"


def test_load_materializes_layers_referenced_but_not_defined(tmp_path) -> None:
    # Real-world DXFs (e.g. cadastral/surveying exports) can have entities
    # on a layer name with no LAYER table entry at all — valid DXF, and
    # AutoCAD auto-creates a default entry for it on open. Reproduces the
    # exact shape of the bug reported against a real file: only "0" (and
    # ezdxf's own "Defpoints") showed up in the layers panel even though
    # the file's entities used many more layer names than that.
    raw = ezdxf.new()
    raw.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "UNDEFINED-LAYER"})
    assert "UNDEFINED-LAYER" not in raw.layers
    path = tmp_path / "undefined_layer.dxf"
    raw.saveas(path)

    doc = DXFDocument.load(str(path))
    names = {info.name for info in doc.iter_layers()}
    assert "UNDEFINED-LAYER" in names
    assert doc.get_layer_color("UNDEFINED-LAYER") == (255, 255, 255)


def test_get_layer_color_resolves_classic_aci_color(doc: DXFDocument) -> None:
    # Most real-world DXFs (cadastral/surveying exports included) color
    # layers the classic way - an AutoCAD Color Index, not true-color RGB.
    doc.layers.add("RED-LAYER", color=1)  # ACI 1 = pure red
    assert doc.get_layer_color("RED-LAYER") == (255, 0, 0)


def test_get_layer_color_prefers_true_color_rgb_over_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("BOTH", color=1)  # ACI red...
    layer.rgb = (10, 20, 30)  # ...but an explicit true-color wins
    assert doc.get_layer_color("BOTH") == (10, 20, 30)


def test_get_layer_color_falls_back_to_white_for_invalid_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("WEIRD")
    layer.dxf.color = 0  # not a valid color index (BYBLOCK, meaningless on a layer)
    assert doc.get_layer_color("WEIRD") == (255, 255, 255)


def test_get_layer_color_ignores_the_off_sign_on_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("OFF-LAYER", color=1)  # ACI 1 = red
    layer.off()  # stores color as -1 internally - still red, just hidden
    assert doc.get_layer_color("OFF-LAYER") == (255, 0, 0)
