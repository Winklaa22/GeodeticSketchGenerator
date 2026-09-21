from __future__ import annotations

from core.table_template import (
    MAX_TABLE_WIDTH_MM,
    CellDef,
    ColumnDef,
    FieldDef,
    Rect,
    RowDef,
    TableTemplate,
    add_column,
    add_field,
    add_row,
    capped_table_width,
    cell_layout,
    default_template,
    delete_column,
    delete_row,
    find_cell_at,
    merge_cells,
    remove_field,
    rename_field,
    resize_column,
    resize_row,
    resolve_cells,
    set_cell,
    table_layout,
    unmerge_cell,
    update_field,
)


def _simple_template() -> TableTemplate:
    return TableTemplate(
        columns=[ColumnDef(0.5), ColumnDef(0.5)],
        rows=[RowDef(10.0), RowDef(5.0)],
        cells=[
            CellDef(row=0, col=0, kind="static", label="A"),
            CellDef(row=0, col=1, kind="static", label="B"),
            CellDef(row=1, col=0, kind="blank"),
            CellDef(row=1, col=1, kind="blank"),
        ],
    )


def test_default_template_has_the_legacy_four_column_grid() -> None:
    template = default_template()
    assert len(template.columns) == 4
    fractions = [c.width_fraction for c in template.columns]
    assert abs(sum(fractions) - 1.0) < 1e-9
    assert abs(template.total_height_mm() - 32.5) < 1e-9


def test_total_height_mm_sums_row_heights() -> None:
    template = _simple_template()
    assert template.total_height_mm() == 15.0


def test_cell_layout_partitions_the_table_without_gaps_or_overlaps() -> None:
    template = _simple_template()
    placed = cell_layout(template, 200.0)
    xs = sorted({round(c.rect.x, 6) for c in placed} | {round(c.rect.right(), 6) for c in placed})
    assert xs[0] == 0.0
    assert xs[-1] == 200.0
    ys = sorted({round(c.rect.y, 6) for c in placed} | {round(c.rect.bottom(), 6) for c in placed})
    assert ys[0] == 0.0
    assert ys[-1] == 15.0


def test_cell_layout_scales_font_size_by_the_scale_factor() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="static", label="A", font_size=2.4)],
    )
    placed = cell_layout(template, 200.0, scale=0.5)
    assert placed[0].font_size == 1.2


def test_cell_layout_respects_row_and_col_spans() -> None:
    template = TableTemplate(
        columns=[ColumnDef(0.5), ColumnDef(0.5)],
        rows=[RowDef(10.0), RowDef(5.0)],
        cells=[CellDef(row=0, col=0, row_span=2, col_span=2, kind="static", label="Merged")],
    )
    placed = cell_layout(template, 200.0)
    cell = placed[0]
    assert cell.rect.w == 200.0
    assert cell.rect.h == 15.0


def test_resolve_cells_static_cell_uses_its_label() -> None:
    template = _simple_template()
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {}, {})
    a_cell = next(c for c in resolved if c.label == "A")
    assert a_cell.text == "A"


def test_resolve_cells_blank_cell_is_always_empty() -> None:
    template = _simple_template()
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {}, {})
    blank_cell = next(c for c in resolved if c.kind == "blank")
    assert blank_cell.text == ""


def test_resolve_cells_field_cell_uses_sheet_scoped_value() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="powiat", label="powiat", show_label=True)],
        fields=[FieldDef(name="powiat", label="Powiat", scope="sheet")],
    )
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {"powiat": "wrocławski"}, {})
    assert resolved[0].text == "powiat wrocławski"


def test_resolve_cells_field_cell_uses_project_scoped_value() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="surveyor")],
        fields=[FieldDef(name="surveyor", scope="project")],
    )
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {"surveyor": "wrong scope"}, {"surveyor": "Lucjan Winkler"})
    assert resolved[0].text == "Lucjan Winkler"


def test_resolve_cells_show_label_prefixes_the_value() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="gmina", label="gmina", show_label=True)],
        fields=[FieldDef(name="gmina")],
    )
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {"gmina": "Trzebnica"}, {})
    assert resolved[0].text == "gmina Trzebnica"


def test_resolve_cells_blank_behavior_hide_omits_empty_field_text() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="gmina", label="gmina", show_label=True)],
        fields=[FieldDef(name="gmina", blank_behavior="hide")],
    )
    placed = cell_layout(template, 200.0)
    resolved = resolve_cells(template, placed, {}, {})
    assert resolved[0].text == ""


def test_resolve_cells_blank_behavior_label_only_falls_back_to_bare_label() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="sketch_number", label="Szkic nr :", show_label=True)],
        fields=[FieldDef(name="sketch_number", blank_behavior="label_only")],
    )
    placed = cell_layout(template, 200.0)
    empty = resolve_cells(template, placed, {}, {})
    assert empty[0].text == "Szkic nr :"
    filled = resolve_cells(template, placed, {"sketch_number": "3"}, {})
    assert filled[0].text == "Szkic nr : 3"


def test_table_layout_offsets_cells_into_the_table_rect() -> None:
    template = _simple_template()
    table_rect = Rect(50.0, 60.0, 200.0, 15.0)
    resolved = table_layout(template, table_rect, {}, {})
    assert min(c.rect.x for c in resolved) == 50.0
    assert min(c.rect.y for c in resolved) == 60.0
    assert max(c.rect.right() for c in resolved) == 250.0


def test_table_layout_caps_the_width_on_an_oversized_sheet_and_stays_left_anchored() -> None:
    template = _simple_template()
    table_rect = Rect(50.0, 60.0, 900.0, 15.0)
    resolved = table_layout(template, table_rect, {}, {})
    assert min(c.rect.x for c in resolved) == 50.0
    assert max(c.rect.right() for c in resolved) == 50.0 + MAX_TABLE_WIDTH_MM


def test_capped_table_width_leaves_a_narrower_table_untouched() -> None:
    assert capped_table_width(150.0) == 150.0


def test_capped_table_width_scales_the_cap_by_the_scale_factor() -> None:
    assert capped_table_width(900.0, scale=0.5) == MAX_TABLE_WIDTH_MM * 0.5


def test_add_row_shifts_cells_below_the_insertion_point() -> None:
    template = _simple_template()
    updated = add_row(template, 1, height_mm=3.0)
    assert len(updated.rows) == 3
    assert updated.rows[1].height_mm == 3.0
    bottom_cells = [c for c in updated.cells if c.row == 2]
    assert {c.label for c in bottom_cells if c.kind == "blank"} == {""}
    assert len(bottom_cells) == 2


def test_delete_row_drops_cells_fully_inside_it_and_shrinks_spans_crossing_it() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(5.0), RowDef(5.0), RowDef(5.0)],
        cells=[
            CellDef(row=0, col=0, row_span=2, kind="static", label="Spans 0-1"),
            CellDef(row=2, col=0, kind="static", label="Row 2 only"),
        ],
    )
    updated = delete_row(template, 1)
    assert len(updated.rows) == 2
    spanning = next(c for c in updated.cells if c.label == "Spans 0-1")
    assert spanning.row == 0 and spanning.row_span == 1
    remaining = next(c for c in updated.cells if c.label == "Row 2 only")
    assert remaining.row == 1


def test_delete_row_refuses_to_drop_the_last_row() -> None:
    template = TableTemplate(columns=[ColumnDef(1.0)], rows=[RowDef(5.0)], cells=[])
    assert delete_row(template, 0) is template


def test_add_column_inserts_and_renormalizes_width_fractions_to_one() -> None:
    template = _simple_template()
    updated = add_column(template, 1, width_fraction=0.5)
    assert len(updated.columns) == 3
    assert abs(sum(c.width_fraction for c in updated.columns) - 1.0) < 1e-9


def test_delete_column_keeps_at_least_one_column() -> None:
    template = TableTemplate(columns=[ColumnDef(1.0)], rows=[RowDef(5.0)], cells=[])
    assert delete_column(template, 0) is template


def test_merge_cells_absorbs_covered_cells_into_one_span() -> None:
    template = _simple_template()
    updated = merge_cells(template, 0, 0, row_span=2, col_span=2)
    assert len(updated.cells) == 1
    merged = updated.cells[0]
    assert merged.row_span == 2 and merged.col_span == 2


def test_unmerge_cell_resets_span_and_fills_the_gap_with_blanks() -> None:
    template = _simple_template()
    merged = merge_cells(template, 0, 0, row_span=2, col_span=2)
    updated = unmerge_cell(merged, 0, 0)
    origin = find_cell_at(updated, 0, 0)
    assert origin.row_span == 1 and origin.col_span == 1
    assert find_cell_at(updated, 1, 1).kind == "blank"
    assert len(updated.cells) == 4


def test_remove_field_blanks_out_cells_that_referenced_it() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="powiat")],
        fields=[FieldDef(name="powiat")],
    )
    updated = remove_field(template, "powiat")
    assert updated.fields == []
    assert updated.cells[0].kind == "blank"
    assert updated.cells[0].field_name == ""


def test_update_field_changes_its_own_properties_without_touching_cells() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="powiat")],
        fields=[FieldDef(name="powiat", label="Powiat", scope="sheet")],
    )
    updated = update_field(template, "powiat", label="District", scope="project")
    assert updated.fields[0].label == "District"
    assert updated.fields[0].scope == "project"
    assert updated.cells[0].field_name == "powiat"


def test_rename_field_updates_cell_references() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, kind="field", field_name="powiat")],
        fields=[FieldDef(name="powiat")],
    )
    updated = rename_field(template, "powiat", "district")
    assert updated.fields[0].name == "district"
    assert updated.cells[0].field_name == "district"


def test_resize_row_updates_height_mm_only() -> None:
    template = _simple_template()
    updated = resize_row(template, 0, 20.0)
    assert updated.rows[0].height_mm == 20.0
    assert updated.rows[1].height_mm == 5.0


def test_resize_column_renormalizes_all_fractions() -> None:
    template = _simple_template()
    updated = resize_column(template, 0, 1.5)
    assert abs(sum(c.width_fraction for c in updated.columns) - 1.0) < 1e-9
    assert updated.columns[0].width_fraction > updated.columns[1].width_fraction


def test_set_cell_replaces_properties_of_the_cell_at_its_origin() -> None:
    template = _simple_template()
    updated = set_cell(template, 0, 0, label="Changed", bold=True)
    cell = find_cell_at(updated, 0, 0)
    assert cell.label == "Changed"
    assert cell.bold is True


def test_add_field_rejects_a_duplicate_name() -> None:
    template = TableTemplate(columns=[ColumnDef(1.0)], rows=[RowDef(5.0)], cells=[], fields=[FieldDef(name="a")])
    try:
        add_field(template, FieldDef(name="a"))
    except ValueError:
        return
    raise AssertionError("expected ValueError for a duplicate field name")


def test_save_and_load_table_template_file_round_trips(tmp_path) -> None:
    from core.project import load_table_template_file, save_table_template_file

    template = TableTemplate(
        columns=[ColumnDef(0.6), ColumnDef(0.4)],
        rows=[RowDef(10.0), RowDef(5.0)],
        cells=[
            CellDef(row=0, col=0, kind="static", label="Left"),
            CellDef(row=0, col=1, row_span=2, kind="field", field_name="powiat", label="powiat", show_label=True),
            CellDef(row=1, col=0, kind="blank"),
        ],
        fields=[FieldDef(name="powiat", label="Powiat", scope="sheet")],
        project_field_values={"should_be": "dropped_on_export"},
    )
    path = str(tmp_path / "template.gsgtable")
    save_table_template_file(path, template)
    loaded = load_table_template_file(path)
    assert loaded.columns == template.columns
    assert loaded.rows == template.rows
    assert loaded.cells == template.cells
    assert loaded.fields == template.fields
    assert loaded.project_field_values == {}


def test_cell_layout_resolves_an_empty_font_id_to_the_table_default() -> None:
    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0), RowDef(10.0)],
        cells=[
            CellDef(row=0, col=0, label="inherits"),
            CellDef(row=1, col=0, label="overrides", font_id="times"),
        ],
        default_font_id="romans",
    )
    placed = {cell.row: cell.font_id for cell in cell_layout(template, 100.0)}
    assert placed[0] == "romans"
    assert placed[1] == "times"


def test_table_default_font_survives_a_template_file_round_trip(tmp_path) -> None:
    from core.project import load_table_template_file, save_table_template_file

    template = TableTemplate(
        columns=[ColumnDef(1.0)],
        rows=[RowDef(10.0)],
        cells=[CellDef(row=0, col=0, label="Left", font_id="isocp", font_size=3.2)],
        default_font_id="times",
    )
    path = str(tmp_path / "fonts.gsgtable")
    save_table_template_file(path, template)
    loaded = load_table_template_file(path)
    assert loaded.default_font_id == "times"
    assert loaded.cells[0].font_id == "isocp"
    assert loaded.cells[0].font_size == 3.2


def test_templates_saved_before_fonts_existed_load_with_defaults(tmp_path) -> None:
    import json

    from core.project import load_table_template_file

    path = tmp_path / "old.gsgtable"
    payload = {
        "version": 1,
        "columns": [{"width_fraction": 1.0}],
        "rows": [{"height_mm": 10.0}],
        "cells": [{"row": 0, "col": 0, "kind": "static", "label": "Left"}],
        "fields": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = load_table_template_file(str(path))
    assert loaded.default_font_id == "calibri"
    assert loaded.cells[0].font_id == ""


def test_load_table_template_file_rejects_malformed_json(tmp_path) -> None:
    from core.exceptions import ProjectFileError
    from core.project import load_table_template_file

    path = tmp_path / "broken.gsgtable"
    path.write_text("{not valid json", encoding="utf-8")
    try:
        load_table_template_file(str(path))
    except ProjectFileError:
        return
    raise AssertionError("expected ProjectFileError for malformed JSON")
