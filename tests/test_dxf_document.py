from __future__ import annotations

import io

import ezdxf
import pytest

from core.dxf_document import DXFDocument


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


def test_new_document_is_empty(doc: DXFDocument) -> None:
    assert doc.entity_count() == 0
    assert doc.layer_count() >= 1


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


def test_add_text_defaults_to_calibri_style(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6)
    entity = doc.get_entity(handle)
    assert entity.dxf.style == "CALIBRI"
    assert doc.drawing.styles.get("CALIBRI").dxf.font == "calibri.ttf"
    assert doc.get_text_font(handle) == "calibri"


def test_add_text_registers_the_requested_font_style(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, font_id="times")
    entity = doc.get_entity(handle)
    assert entity.dxf.style == "TIMES"
    assert doc.drawing.styles.get("TIMES").dxf.font == "times.ttf"
    assert doc.get_text_font(handle) == "times"


def test_add_text_renders_distinct_fonts_when_the_real_ones_are_unavailable(doc: DXFDocument) -> None:
    from ezdxf.fonts import fonts as ezdxf_fonts

    if ezdxf_fonts.find_best_match(family="Liberation Sans") is None:
        pytest.skip("no fallback-capable fonts installed on this machine")

    resolved_filenames = set()
    for font_id in ("romans", "complex", "arial", "times", "calibri"):
        handle = doc.add_text("A", (0.0, 0.0), height=1.0, font_id=font_id)
        entity = doc.get_entity(handle)
        face = ezdxf_fonts.get_entity_font_face(entity, doc.drawing)
        resolved_filenames.add(face.filename)
    # On a machine with none of the literal font files installed, ezdxf would silently
    # collapse every unresolved font to the same single default - this is the bug this
    # module works around, so at least some of the five must resolve differently.
    assert len(resolved_filenames) > 1


def test_italic_text_renders_a_genuinely_different_font_than_upright(doc: DXFDocument) -> None:
    from ezdxf.fonts import fonts as ezdxf_fonts

    if ezdxf_fonts.find_best_match(family="Liberation Sans") is None:
        pytest.skip("no fallback-capable fonts installed on this machine")

    # ezdxf's drawing add-on ignores the STYLE table's oblique angle for plain TEXT
    # entities, so italic must resolve to an actually different font file to be visible.
    for font_id in ("romans", "isocp", "simplex", "txt", "complex", "arial", "times", "calibri"):
        upright = doc.add_text("A", (0.0, 0.0), height=1.0, font_id=font_id, italic=False)
        italic = doc.add_text("A", (1.0, 0.0), height=1.0, font_id=font_id, italic=True)
        upright_face = ezdxf_fonts.get_entity_font_face(doc.get_entity(upright), doc.drawing)
        italic_face = ezdxf_fonts.get_entity_font_face(doc.get_entity(italic), doc.drawing)
        assert upright_face.filename != italic_face.filename, font_id


def test_ensure_text_style_is_idempotent(doc: DXFDocument) -> None:
    doc.ensure_text_style("isocp")
    doc.ensure_text_style("isocp")
    assert len([s for s in doc.drawing.styles if s.dxf.name == "ISOCP"]) == 1


def test_add_text_italic_uses_a_separate_style_with_an_oblique_angle(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, font_id="times", italic=True)
    entity = doc.get_entity(handle)
    assert entity.dxf.style == "TIMES_ITALIC"
    assert doc.drawing.styles.get("TIMES_ITALIC").dxf.oblique == 15.0
    assert doc.get_text_font(handle) == "times"
    assert doc.get_text_italic(handle) is True


def test_set_text_font_preserves_the_italic_flag(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, font_id="times", italic=True)
    doc.set_text_font(handle, "arial")
    assert doc.get_text_font(handle) == "arial"
    assert doc.get_text_italic(handle) is True


def test_set_text_italic_preserves_the_font(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, font_id="times")
    doc.set_text_italic(handle, True)
    assert doc.get_text_font(handle) == "times"
    assert doc.get_text_italic(handle) is True
    doc.set_text_italic(handle, False)
    assert doc.get_text_italic(handle) is False


def test_add_text_lineweight_defaults_to_bylayer(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6)
    assert doc.get_text_lineweight_mm(handle) is None


def test_add_text_registers_the_requested_lineweight(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, lineweight_mm=0.25)
    assert doc.get_entity(handle).dxf.lineweight == 25
    assert doc.get_text_lineweight_mm(handle) == 0.25


def test_set_text_lineweight_mm_round_trips_and_clears_back_to_bylayer(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6)
    doc.set_text_lineweight_mm(handle, 0.35)
    assert doc.get_text_lineweight_mm(handle) == 0.35
    doc.set_text_lineweight_mm(handle, None)
    assert doc.get_text_lineweight_mm(handle) is None


def test_all_text_handles_returns_only_text_entities(doc: DXFDocument) -> None:
    text_handle = doc.add_text("42", (0.0, 0.0), height=0.6)
    doc.add_line((0.0, 0.0), (1.0, 1.0))
    doc.add_point((0.0, 0.0))
    assert doc.all_text_handles() == [text_handle]


def test_set_text_font_updates_the_entity_style(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6, font_id="romans")
    doc.set_text_font(handle, "calibri")
    assert doc.get_text_font(handle) == "calibri"
    assert doc.get_entity(handle).dxf.style == "CALIBRI"


def test_get_text_font_falls_back_to_default_for_an_unknown_style(doc: DXFDocument) -> None:
    handle = doc.add_text("42", (0.0, 0.0), height=0.6)
    doc.get_entity(handle).dxf.style = "Standard"
    assert doc.get_text_font(handle) == "calibri"


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
    doc.ensure_layer("SURVEY")
    assert "SURVEY" in doc.layers


def test_add_point_auto_creates_its_layer(doc: DXFDocument) -> None:
    assert "SURVEY" not in doc.layers
    doc.add_point((0.0, 0.0), layer="SURVEY")
    assert "SURVEY" in doc.layers


def test_unlink_entity_removes_it_from_modelspace_but_keeps_it_in_the_database(doc: DXFDocument) -> None:
    handle = doc.add_point((0.0, 0.0))
    entity = doc.unlink_entity(handle)
    assert doc.entity_count() == 0
    assert doc.get_entity(handle) is not None
    assert entity.dxf.handle == handle


def test_unlink_entity_returns_none_for_unknown_handle(doc: DXFDocument) -> None:
    assert doc.unlink_entity("does-not-exist") is None


def test_unlink_entity_returns_none_if_already_unlinked(doc: DXFDocument) -> None:
    handle = doc.add_point((0.0, 0.0))
    doc.unlink_entity(handle)
    assert doc.unlink_entity(handle) is None


def test_relink_entity_puts_a_previously_unlinked_entity_back(doc: DXFDocument) -> None:
    handle = doc.add_point((1.0, 2.0))
    doc.unlink_entity(handle)
    assert doc.entity_count() == 0
    doc.relink_entity(handle)
    assert doc.entity_count() == 1
    assert doc.get_entity(handle).dxf.handle == handle


def test_relink_entity_is_a_noop_for_an_already_linked_entity(doc: DXFDocument) -> None:
    handle = doc.add_point((1.0, 2.0))
    doc.relink_entity(handle)
    assert doc.entity_count() == 1


def test_relink_entity_is_a_noop_for_an_unknown_handle(doc: DXFDocument) -> None:
    doc.relink_entity("does-not-exist")
    assert doc.entity_count() == 0


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


def test_entity_center_of_a_point_is_its_own_location(doc: DXFDocument) -> None:
    handle = doc.add_point((3.0, 4.0))
    assert doc.entity_center(handle) == pytest.approx((3.0, 4.0))


def test_entity_center_of_a_line_is_its_midpoint(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (10.0, 0.0))
    assert doc.entity_center(handle) == pytest.approx((5.0, 0.0))


def test_entity_center_of_a_circle_is_its_own_center(doc: DXFDocument) -> None:
    handle = doc.add_circle((5.0, 5.0), radius=2.0)
    assert doc.entity_center(handle) == pytest.approx((5.0, 5.0))


def test_entity_center_raises_for_unknown_handle(doc: DXFDocument) -> None:
    with pytest.raises(KeyError):
        doc.entity_center("does-not-exist")


def test_find_similar_matches_same_type_layer_and_color(doc: DXFDocument) -> None:
    doc.add_layer("A", rgb=(255, 0, 0))
    doc.add_layer("B", rgb=(0, 255, 0))
    h1 = doc.add_text("t1", (0.0, 0.0), height=0.5, layer="A")
    h2 = doc.add_text("t2", (5.0, 0.0), height=0.5, layer="A")
    h3 = doc.add_text("t3", (10.0, 0.0), height=0.5, layer="B")
    h4 = doc.add_line((0.0, 5.0), (5.0, 5.0), layer="A")
    assert set(doc.find_similar(h1)) == {h1, h2}
    assert h3 not in doc.find_similar(h1)
    assert h4 not in doc.find_similar(h1)


def test_find_similar_excludes_same_type_and_layer_but_different_color(doc: DXFDocument) -> None:
    doc.add_layer("A", rgb=(255, 0, 0))
    h1 = doc.add_point((0.0, 0.0), layer="A")
    h2 = doc.add_point((1.0, 0.0), layer="A")
    doc.set_entity_color(h2, (0, 0, 255))
    assert doc.find_similar(h1) == [h1]


def test_find_similar_raises_for_unknown_handle(doc: DXFDocument) -> None:
    with pytest.raises(KeyError):
        doc.find_similar("does-not-exist")


def test_add_layer_creates_it_with_the_given_color(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(200, 50, 50))
    assert "SURVEY" in doc.layers
    assert doc.get_layer_color("SURVEY") == (200, 50, 50)


def test_add_layer_is_idempotent(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.add_layer("SURVEY")
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


def test_set_layer_color_also_sets_a_classic_aci_fallback(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.set_layer_color("SURVEY", (255, 0, 0))
    layer = doc.layers.get("SURVEY")
    assert layer.dxf.color == 1


def test_set_layer_color_preserves_visibility_when_recoloring_a_hidden_layer(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.set_layer_visible("SURVEY", False)
    doc.set_layer_color("SURVEY", (255, 0, 0))
    assert doc.is_layer_visible("SURVEY") is False


def test_layer_color_survives_a_pre_true_color_dxf_version(tmp_path) -> None:
    raw = ezdxf.new(dxfversion="AC1015")
    path = tmp_path / "r2000.dxf"
    raw.saveas(path)

    doc = DXFDocument.load(str(path))
    doc.add_layer("SURVEY")
    doc.set_layer_color("SURVEY", (255, 0, 0))
    assert doc.get_layer_color("SURVEY") == (255, 0, 0)

    reloaded = DXFDocument.from_text(doc.to_text())
    assert reloaded.get_layer_color("SURVEY") == (255, 0, 0)


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
    raw = ezdxf.new()
    raw.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "UNDEFINED-LAYER"})
    assert "UNDEFINED-LAYER" not in raw.layers
    path = tmp_path / "undefined_layer.dxf"
    raw.saveas(path)

    doc = DXFDocument.load(str(path))
    names = {info.name for info in doc.iter_layers()}
    assert "UNDEFINED-LAYER" in names
    assert doc.get_layer_color("UNDEFINED-LAYER") == (255, 255, 255)


def test_to_text_then_from_text_round_trips_entities_and_layers(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(9, 9, 9))
    doc.add_line((0.0, 0.0), (1.0, 1.0), layer="SURVEY")
    doc.add_point((2.0, 2.0), layer="SURVEY")

    content = doc.to_text()
    assert isinstance(content, str) and len(content) > 0

    restored = DXFDocument.from_text(content)
    assert restored.entity_count() == 2
    assert "SURVEY" in restored.layers
    assert restored.get_layer_color("SURVEY") == (9, 9, 9)


def test_from_text_raises_dxf_error_for_garbage_content() -> None:
    with pytest.raises(ezdxf.DXFError):
        DXFDocument.from_text("this is not a dxf file at all")


def test_from_text_materializes_layers_referenced_but_not_defined() -> None:
    raw = ezdxf.new()
    raw.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "UNDEFINED-LAYER"})
    stream_content = _write_to_text(raw)

    doc = DXFDocument.from_text(stream_content)
    names = {info.name for info in doc.iter_layers()}
    assert "UNDEFINED-LAYER" in names


def _write_to_text(drawing) -> str:
    stream = io.StringIO()
    drawing.write(stream)
    return stream.getvalue()


def test_get_layer_color_resolves_classic_aci_color(doc: DXFDocument) -> None:
    doc.layers.add("RED-LAYER", color=1)
    assert doc.get_layer_color("RED-LAYER") == (255, 0, 0)


def test_get_layer_color_prefers_true_color_rgb_over_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("BOTH", color=1)
    layer.rgb = (10, 20, 30)
    assert doc.get_layer_color("BOTH") == (10, 20, 30)


def test_get_layer_color_falls_back_to_white_for_invalid_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("WEIRD")
    layer.dxf.color = 0
    assert doc.get_layer_color("WEIRD") == (255, 255, 255)


def test_get_layer_color_ignores_the_off_sign_on_aci(doc: DXFDocument) -> None:
    layer = doc.layers.add("OFF-LAYER", color=1)
    layer.off()
    assert doc.get_layer_color("OFF-LAYER") == (255, 0, 0)
