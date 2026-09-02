from __future__ import annotations

from core.title_block import (
    COL_A_FRACTION,
    COL_B_FRACTION,
    COL_C_FRACTION,
    COL_D_FRACTION,
    Rect,
    SheetTitleBlockFields,
    TitleBlockProfile,
    cell_layout,
    resolve_cells,
    split_printable_rect,
    title_block_layout,
)


def test_column_fractions_sum_to_one() -> None:
    assert abs((COL_A_FRACTION + COL_B_FRACTION + COL_C_FRACTION + COL_D_FRACTION) - 1.0) < 1e-9


def test_cell_layout_returns_ten_cells() -> None:
    assert len(cell_layout(200.0)) == 10


def test_cell_layout_partitions_the_table_without_gaps_or_overlaps() -> None:
    cells = cell_layout(200.0)
    xs = sorted({round(c.rect.x, 6) for c in cells} | {round(c.rect.right(), 6) for c in cells})
    assert xs[0] == 0.0
    assert xs[-1] == 200.0
    ys = sorted({round(c.rect.y, 6) for c in cells} | {round(c.rect.bottom(), 6) for c in cells})
    assert ys[0] == 0.0
    total_height = max(c.rect.bottom() for c in cells)
    assert ys[-1] == round(total_height, 6)


def test_cell_layout_scales_rows_and_fonts_by_the_scale_factor() -> None:
    unscaled = cell_layout(200.0, scale=1.0)
    scaled = cell_layout(200.0, scale=2.0)
    total_unscaled = max(c.rect.bottom() for c in unscaled)
    total_scaled = max(c.rect.bottom() for c in scaled)
    assert abs(total_scaled - total_unscaled * 2.0) < 1e-9
    # column fractions (dimensionless) are unaffected by scale
    assert unscaled[1].rect.w == scaled[1].rect.w


def test_resolve_cells_omits_blank_address_subfields() -> None:
    cells = cell_layout(200.0)
    fields = SheetTitleBlockFields(powiat="wrocławski", gmina="", obreb="KOBIERZYCE", dz_nr="394")
    resolved = resolve_cells(cells, TitleBlockProfile(), fields)
    address_cell = next(c for c in resolved if c.field == "address_block")
    assert address_cell.text == "powiat wrocławski\nobręb KOBIERZYCE\ndz. nr 394"


def test_resolve_cells_builds_the_surveyor_block() -> None:
    cells = cell_layout(200.0)
    profile = TitleBlockProfile(
        surveyor_title="Geodeta", surveyor_name="",
        license_text="",
    )
    resolved = resolve_cells(cells, profile, SheetTitleBlockFields())
    surveyor_cell = next(c for c in resolved if c.field == "surveyor_block")
    assert surveyor_cell.text == ""


def test_resolve_cells_sketch_number_falls_back_to_bare_label() -> None:
    cells = cell_layout(200.0)
    resolved = resolve_cells(cells, TitleBlockProfile(), SheetTitleBlockFields())
    sketch_cell = next(c for c in resolved if c.field == "sketch_number")
    assert sketch_cell.text == "Szkic nr :"

    filled = resolve_cells(cells, TitleBlockProfile(), SheetTitleBlockFields(sketch_number="3"))
    sketch_cell = next(c for c in filled if c.field == "sketch_number")
    assert sketch_cell.text == "Szkic nr : 3"


def test_resolve_cells_blank_cell_is_always_empty() -> None:
    cells = cell_layout(200.0)
    resolved = resolve_cells(cells, TitleBlockProfile(), SheetTitleBlockFields())
    blank_cell = next(c for c in resolved if c.kind == "blank")
    assert blank_cell.text == ""


def test_title_block_layout_offsets_cells_into_the_table_rect() -> None:
    table_rect = Rect(50.0, 60.0, 200.0, 31.0)
    cells = title_block_layout(table_rect, TitleBlockProfile(), SheetTitleBlockFields())
    assert min(c.rect.x for c in cells) == 50.0
    assert min(c.rect.y for c in cells) == 60.0
    assert max(c.rect.right() for c in cells) == 250.0


def test_split_printable_rect_carves_the_table_off_the_end() -> None:
    printable = Rect(0.0, 0.0, 200.0, 100.0)
    map_rect, table_rect = split_printable_rect(printable, 30.0)
    assert map_rect.h == 70.0
    assert table_rect.h == 30.0
    assert table_rect.y == map_rect.bottom()
    assert map_rect.w == table_rect.w == printable.w


def test_split_printable_rect_clamps_when_table_height_exceeds_printable() -> None:
    printable = Rect(0.0, 0.0, 200.0, 10.0)
    map_rect, table_rect = split_printable_rect(printable, 30.0)
    assert map_rect.h == 0.0
    assert table_rect.h == 10.0
