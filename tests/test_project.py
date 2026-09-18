from __future__ import annotations

import json

import pytest

from core.exceptions import ProjectFileError
from core.project import (
    CableState,
    CellDefState,
    ColumnState,
    DelimiterState,
    FieldDefState,
    HeightsState,
    LayerDefState,
    LayerState,
    LayoutState,
    PipeState,
    PointsState,
    ProjectState,
    RowState,
    SelectionState,
    SheetState,
    TableTemplateState,
    default_project_name,
    load_project,
    open_any,
    project_path_if_saved,
    save_project,
)


def test_save_then_load_round_trips_every_field(tmp_path) -> None:
    state = ProjectState(
        name="Ludgierzowice",
        txt_file_path="C:/data/points.txt",
        dxf_file_path="C:/data/drawing.dxf",
        dxf_content="0\nSECTION\n2\nHEADER\n0\nENDSEC\n0\nEOF\n",
        draw_modes=["lines", "heights"],
        delimiter=DelimiterState(mode="tab", swap_xy=False, cabinet_mode=True),
        points=PointsState(numbers_enabled=True, font_size=0.8, diameter=0.1, layer_name="RURA"),
        heights=HeightsState(font_size=0.5, frequency=3, layer_name="RZEDNE"),
        cable=CableState(font_size=0.7, frequency=2, marks_text="CBL"),
        pipe=PipeState(width=0.2),
        selection=SelectionState(mode="range", separate_text="1,2,3", range_text="1-10"),
        layer=LayerState(
            layers=[LayerDefState(name="RURA", rgb=(200, 30, 40)), LayerDefState(name="RZEDNE", rgb=(30, 200, 40))],
            default_name="RURA",
        ),
        layout=LayoutState(
            sheets=[
                SheetState(
                    name="Sytuacja", page_key="a2", landscape=False, scale_denominator=250,
                    field_values={
                        "powiat": "wrocławski", "gmina": "Kobierzyce", "obreb": "KOBIERZYCE",
                        "dz_nr": "394", "sketch_number": "1",
                    },
                ),
                SheetState(name="Detal", color_mode="monochrome", center_x=12.0, center_y=-4.5),
            ],
            active_index=1,
        ),
    )
    path = str(tmp_path / "project.gsgproj")
    save_project(path, state)
    loaded = load_project(path)
    assert loaded == state


def test_dxf_content_defaults_to_none_when_no_dxf_was_loaded(tmp_path) -> None:
    path = str(tmp_path / "no_dxf.gsgproj")
    save_project(path, ProjectState(name="Blank"))
    loaded = load_project(path)
    assert loaded.dxf_content is None


def test_load_missing_file_raises_project_file_error(tmp_path) -> None:
    with pytest.raises(ProjectFileError):
        load_project(str(tmp_path / "does-not-exist.gsgproj"))


def test_load_malformed_json_raises_project_file_error(tmp_path) -> None:
    path = tmp_path / "broken.gsgproj"
    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_load_non_object_json_raises_project_file_error(tmp_path) -> None:
    path = tmp_path / "list.gsgproj"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_load_fills_in_missing_sections_with_defaults(tmp_path) -> None:
    path = tmp_path / "minimal.gsgproj"
    path.write_text(json.dumps({"txt_file_path": "a.txt"}), encoding="utf-8")
    loaded = load_project(str(path))
    assert loaded.txt_file_path == "a.txt"
    assert loaded == ProjectState(name="Untitled", txt_file_path="a.txt")


def test_load_rejects_unknown_field_types(tmp_path) -> None:
    path = tmp_path / "bad_field.gsgproj"
    path.write_text(json.dumps({"points": {"font_size": "not-a-number-but-also-not-castable[]"}}), encoding="utf-8")
    path.write_text(json.dumps({"points": {"font_size": 0.6, "bogus_extra_field": 1}}), encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_load_defaults_the_layout_for_projects_saved_before_sheets(tmp_path) -> None:
    path = tmp_path / "pre_sheets.gsgproj"
    path.write_text(json.dumps({"name": "Old", "draw_modes": ["plines"]}), encoding="utf-8")
    layout = load_project(str(path)).layout
    assert layout == LayoutState()
    assert [sheet.name for sheet in layout.sheets] == ["Sheet 1"]
    assert layout.active_index is None


def test_load_drops_an_active_index_that_points_past_the_sheets(tmp_path) -> None:
    path = tmp_path / "bad_active.gsgproj"
    payload = {"layout": {"sheets": [{"name": "Only"}], "active_index": 5}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert load_project(str(path)).layout.active_index is None


def test_load_keeps_an_empty_sheet_list(tmp_path) -> None:
    path = tmp_path / "no_sheets.gsgproj"
    path.write_text(json.dumps({"layout": {"sheets": []}}), encoding="utf-8")
    layout = load_project(str(path)).layout
    assert layout.sheets == []
    assert layout.active_index is None


def test_load_fills_in_sheet_fields_left_out_of_the_file(tmp_path) -> None:
    path = tmp_path / "partial_sheet.gsgproj"
    payload = {"layout": {"sheets": [{"name": "Detal", "page_key": "a1"}], "active_index": 0}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    sheet = load_project(str(path)).layout.sheets[0]
    assert sheet == SheetState(name="Detal", page_key="a1")


def test_load_ignores_unknown_sheet_fields_for_forward_compatibility(tmp_path) -> None:
    path = tmp_path / "unknown_sheet_field.gsgproj"
    path.write_text(json.dumps({"layout": {"sheets": [{"name": "Only", "bogus": 1}]}}), encoding="utf-8")
    sheet = load_project(str(path)).layout.sheets[0]
    assert sheet.name == "Only"


def test_load_drops_legacy_title_block_fields_from_old_sheets(tmp_path) -> None:
    payload = {"layout": {"sheets": [{
        "name": "Sytuacja", "powiat": "wrocławski", "gmina": "Kobierzyce",
        "obreb": "KOBIERZYCE", "dz_nr": "394", "sketch_number": "1",
    }]}}
    path = tmp_path / "legacy_title_block.gsgproj"
    path.write_text(json.dumps(payload), encoding="utf-8")
    sheet = load_project(str(path)).layout.sheets[0]
    assert sheet.name == "Sytuacja"
    assert sheet.field_values == {}


def test_table_template_survives_a_project_round_trip(tmp_path) -> None:
    template = TableTemplateState(
        columns=[ColumnState(0.5), ColumnState(0.5)],
        rows=[RowState(10.0)],
        cells=[
            CellDefState(row=0, col=0, kind="static", label="Left"),
            CellDefState(row=0, col=1, kind="field", field_name="surveyor", label="surveyor", show_label=True),
        ],
        fields=[FieldDefState(name="surveyor", label="Surveyor", scope="project")],
        project_field_values={"surveyor": "Lucjan Winkler"},
    )
    state = ProjectState(name="WithTemplate", table_template=template)
    path = str(tmp_path / "with_template.gsgproj")
    save_project(path, state)
    assert load_project(path) == state


def test_load_defaults_the_table_template_for_projects_saved_before_this_feature(tmp_path) -> None:
    path = tmp_path / "no_table_template.gsgproj"
    path.write_text(json.dumps({"name": "Old"}), encoding="utf-8")
    assert load_project(str(path)).table_template == TableTemplateState()


def test_load_rejects_unknown_table_template_field_types(tmp_path) -> None:
    path = tmp_path / "bad_table_template.gsgproj"
    payload = {"table_template": {"columns": [{"width_fraction": 0.5, "bogus": 1}]}}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ProjectFileError):
        load_project(str(path))


def test_open_any_loads_a_gsgproj_as_is(tmp_path) -> None:
    state = ProjectState(name="Real", draw_modes=["pipe"])
    path = str(tmp_path / "real.gsgproj")
    save_project(path, state)
    assert open_any(path) == state


def test_load_reads_pre_multi_select_single_draw_mode(tmp_path) -> None:
    path = tmp_path / "legacy.gsgproj"
    path.write_text(json.dumps({"draw_mode": "pipe"}), encoding="utf-8")
    assert load_project(str(path)).draw_modes == ["pipe"]


def test_load_reads_pre_multi_layer_single_layer(tmp_path) -> None:
    path = tmp_path / "legacy_layer.gsgproj"
    path.write_text(json.dumps({"layer": {"name": "RURA", "rgb": [200, 30, 40]}}), encoding="utf-8")
    layer = load_project(str(path)).layer
    assert layer.layers == [LayerDefState(name="RURA", rgb=(200, 30, 40))]
    assert layer.default_name == "RURA"


def test_open_any_wraps_a_bare_dxf_in_a_fresh_project(tmp_path) -> None:
    path = str(tmp_path / "drawing.dxf")
    (tmp_path / "drawing.dxf").write_text("", encoding="utf-8")
    state = open_any(path)
    assert state.name == "drawing"
    assert state.dxf_file_path == path
    assert state.txt_file_path == ""


def test_open_any_wraps_a_bare_txt_in_a_fresh_project(tmp_path) -> None:
    path = str(tmp_path / "points.txt")
    (tmp_path / "points.txt").write_text("", encoding="utf-8")
    state = open_any(path)
    assert state.name == "points"
    assert state.txt_file_path == path
    assert state.dxf_file_path == ""


def test_open_any_rejects_an_unsupported_extension(tmp_path) -> None:
    path = str(tmp_path / "notes.pdf")
    with pytest.raises(ProjectFileError):
        open_any(path)


def test_project_path_if_saved() -> None:
    assert project_path_if_saved("C:/a/project.gsgproj") == "C:/a/project.gsgproj"
    assert project_path_if_saved("C:/a/drawing.dxf") is None
    assert project_path_if_saved("C:/a/points.txt") is None


def test_default_project_name_prefers_dxf_then_txt_then_untitled() -> None:
    assert default_project_name("C:/a/points.txt", "C:/b/drawing.dxf") == "drawing"
    assert default_project_name("C:/a/points.txt", "") == "points"
    assert default_project_name("", "") == "Untitled"


def test_the_model_views_rotation_is_written_to_the_project_file(tmp_path) -> None:
    state = ProjectState(name="Turned")
    state.layout.model_rotation = 35.0
    path = tmp_path / "turned.gsgproj"

    save_project(str(path), state)

    assert load_project(str(path)).layout.model_rotation == 35.0


def test_a_project_saved_before_the_model_rotation_existed_opens_upright(tmp_path) -> None:
    path = tmp_path / "old.gsgproj"
    payload = json.loads(json.dumps({"version": 1, "name": "Old", "layout": {"sheets": [], "active_index": None}}))
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_project(str(path)).layout.model_rotation == 0.0


def test_the_model_views_zoom_and_pan_are_written_to_the_project_file(tmp_path) -> None:
    state = ProjectState(name="Panned")
    state.layout.model_zoom = 3.5
    state.layout.model_center = (120.0, -40.0)
    path = tmp_path / "panned.gsgproj"

    save_project(str(path), state)
    reloaded = load_project(str(path))

    assert reloaded.layout.model_zoom == 3.5
    assert reloaded.layout.model_center == (120.0, -40.0)


def test_a_project_saved_before_the_model_camera_existed_opens_fitted(tmp_path) -> None:
    path = tmp_path / "old.gsgproj"
    payload = json.loads(json.dumps({"version": 1, "name": "Old", "layout": {"sheets": [], "active_index": None}}))
    path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = load_project(str(path))

    assert reloaded.layout.model_zoom == 1.0
    assert reloaded.layout.model_center is None


def test_a_malformed_model_camera_falls_back_to_the_fit(tmp_path) -> None:
    path = tmp_path / "bad.gsgproj"
    payload = {
        "version": 1,
        "name": "Bad",
        "layout": {"sheets": [], "active_index": None, "model_zoom": -1.0, "model_center": "nope"},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    reloaded = load_project(str(path))

    assert reloaded.layout.model_zoom == 1.0
    assert reloaded.layout.model_center is None
