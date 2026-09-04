from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, List, Optional

BORDER_WIDTH_MM = 0.35
CELL_PADDING_MM = 1.5

# Columns are fractions of whatever width they're laid out in, so without a cap the table
# just keeps stretching wider on a bigger sheet. This caps it at the A4 landscape printable
# width (297 - 2x10mm margin), the size it always had on the app's default page - it stays
# that size and sits at the left edge on bigger sheets instead of growing to fill them.
MAX_TABLE_WIDTH_MM = 277.0

HEADER_FONT_MM = 2.0
BODY_FONT_MM = 2.4

_ROW_HEADER_MM = 8.5
_ROW_POMIERZYL_MM = 15.0
_ROW_SPRAWDZIL_MM = 9.0

_COL_A_FRACTION = 0.10
_COL_B_FRACTION = 0.38
_COL_C_FRACTION = 0.24
_COL_D_FRACTION = 0.28


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    w: float
    h: float

    def right(self) -> float:
        return self.x + self.w

    def bottom(self) -> float:
        return self.y + self.h


@dataclass(frozen=True)
class ColumnDef:
    width_fraction: float = 0.25


@dataclass(frozen=True)
class RowDef:
    height_mm: float = 8.0


@dataclass(frozen=True)
class FieldDef:
    name: str
    label: str = ""
    scope: str = "sheet"
    blank_behavior: str = "hide"


@dataclass(frozen=True)
class CellDef:
    row: int
    col: int
    row_span: int = 1
    col_span: int = 1
    kind: str = "static"
    label: str = ""
    field_name: str = ""
    show_label: bool = False
    align: str = "left"
    valign: str = "top"
    font_size: float = BODY_FONT_MM
    bold: bool = False
    italic: bool = False
    image_path: str = ""


@dataclass(frozen=True)
class PlacedCell(CellDef):
    rect: Rect = Rect(0.0, 0.0, 0.0, 0.0)


@dataclass(frozen=True)
class ResolvedCell(PlacedCell):
    text: str = ""


@dataclass(frozen=True)
class TableTemplate:
    columns: List[ColumnDef]
    rows: List[RowDef]
    cells: List[CellDef]
    fields: List[FieldDef] = field(default_factory=list)
    project_field_values: Dict[str, str] = field(default_factory=dict)

    def total_height_mm(self) -> float:
        return sum(row.height_mm for row in self.rows)


def _cell_kwargs(cell: CellDef) -> dict:
    return {
        "row": cell.row,
        "col": cell.col,
        "row_span": cell.row_span,
        "col_span": cell.col_span,
        "kind": cell.kind,
        "label": cell.label,
        "field_name": cell.field_name,
        "show_label": cell.show_label,
        "align": cell.align,
        "valign": cell.valign,
        "font_size": cell.font_size,
        "bold": cell.bold,
        "italic": cell.italic,
        "image_path": cell.image_path,
    }


def _cumulative_edges(sizes: Iterable[float]) -> List[float]:
    edges = [0.0]
    total = 0.0
    for size in sizes:
        total += size
        edges.append(total)
    return edges


def cell_layout(template: TableTemplate, table_width: float, scale: float = 1.0) -> List[PlacedCell]:
    col_edges = _cumulative_edges(column.width_fraction * table_width for column in template.columns)
    row_edges = _cumulative_edges(row.height_mm * scale for row in template.rows)
    placed = []
    for cell in template.cells:
        x0 = col_edges[cell.col]
        x1 = col_edges[min(cell.col + cell.col_span, len(col_edges) - 1)]
        y0 = row_edges[cell.row]
        y1 = row_edges[min(cell.row + cell.row_span, len(row_edges) - 1)]
        kwargs = _cell_kwargs(cell)
        kwargs["font_size"] = cell.font_size * scale
        placed.append(PlacedCell(**kwargs, rect=Rect(x0, y0, x1 - x0, y1 - y0)))
    return placed


def _resolve_cell_text(
    cell: CellDef,
    fields_by_name: Dict[str, FieldDef],
    sheet_values: Dict[str, str],
    project_values: Dict[str, str],
) -> str:
    if cell.kind in ("blank", "image"):
        return ""
    if cell.kind == "field":
        field_def = fields_by_name.get(cell.field_name)
        if field_def is None:
            return ""
        values = sheet_values if field_def.scope == "sheet" else project_values
        value = values.get(field_def.name, "")
        if not value:
            return cell.label if field_def.blank_behavior == "label_only" else ""
        return f"{cell.label} {value}" if cell.show_label and cell.label else value
    return cell.label


def resolve_cells(
    template: TableTemplate,
    placed: List[PlacedCell],
    sheet_values: Dict[str, str],
    project_values: Dict[str, str],
) -> List[ResolvedCell]:
    fields_by_name = {field_def.name: field_def for field_def in template.fields}
    resolved = []
    for cell in placed:
        text = _resolve_cell_text(cell, fields_by_name, sheet_values, project_values)
        resolved.append(ResolvedCell(**_cell_kwargs(cell), rect=cell.rect, text=text))
    return resolved


def capped_table_width(available_mm: float, scale: float = 1.0) -> float:
    return min(available_mm, MAX_TABLE_WIDTH_MM * scale)


def table_layout(
    template: TableTemplate,
    table_rect: Rect,
    sheet_values: Dict[str, str],
    project_values: Dict[str, str],
    scale: float = 1.0,
) -> List[ResolvedCell]:
    width = capped_table_width(table_rect.w, scale)
    placed = cell_layout(template, width, scale)
    resolved = resolve_cells(template, placed, sheet_values, project_values)
    return [
        replace(cell, rect=Rect(cell.rect.x + table_rect.x, cell.rect.y + table_rect.y, cell.rect.w, cell.rect.h))
        for cell in resolved
    ]


def _renormalize_columns(columns: List[ColumnDef]) -> List[ColumnDef]:
    total = sum(column.width_fraction for column in columns) or 1.0
    return [ColumnDef(width_fraction=column.width_fraction / total) for column in columns]


def add_row(template: TableTemplate, at_index: int, height_mm: float = 8.0) -> TableTemplate:
    at_index = max(0, min(at_index, len(template.rows)))
    rows = list(template.rows)
    rows.insert(at_index, RowDef(height_mm=height_mm))
    cells = [replace(cell, row=cell.row + 1) if cell.row >= at_index else cell for cell in template.cells]
    cells.extend(CellDef(row=at_index, col=col, kind="blank") for col in range(len(template.columns)))
    return replace(template, rows=rows, cells=cells)


def delete_row(template: TableTemplate, index: int) -> TableTemplate:
    if len(template.rows) <= 1 or not 0 <= index < len(template.rows):
        return template
    rows = [row for i, row in enumerate(template.rows) if i != index]
    cells = []
    for cell in template.cells:
        top, bottom = cell.row, cell.row + cell.row_span
        if index < top:
            cells.append(replace(cell, row=cell.row - 1))
        elif index >= bottom:
            cells.append(cell)
        elif cell.row_span == 1:
            continue
        else:
            cells.append(replace(cell, row_span=cell.row_span - 1))
    return replace(template, rows=rows, cells=cells)


def add_column(template: TableTemplate, at_index: int, width_fraction: float = 0.25) -> TableTemplate:
    at_index = max(0, min(at_index, len(template.columns)))
    columns = _renormalize_columns(
        [*template.columns[:at_index], ColumnDef(width_fraction=width_fraction), *template.columns[at_index:]]
    )
    cells = [replace(cell, col=cell.col + 1) if cell.col >= at_index else cell for cell in template.cells]
    cells.extend(CellDef(row=row, col=at_index, kind="blank") for row in range(len(template.rows)))
    return replace(template, columns=columns, cells=cells)


def delete_column(template: TableTemplate, index: int) -> TableTemplate:
    if len(template.columns) <= 1 or not 0 <= index < len(template.columns):
        return template
    columns = _renormalize_columns([col for i, col in enumerate(template.columns) if i != index])
    cells = []
    for cell in template.cells:
        left, right = cell.col, cell.col + cell.col_span
        if index < left:
            cells.append(replace(cell, col=cell.col - 1))
        elif index >= right:
            cells.append(cell)
        elif cell.col_span == 1:
            continue
        else:
            cells.append(replace(cell, col_span=cell.col_span - 1))
    return replace(template, columns=columns, cells=cells)


def resize_row(template: TableTemplate, index: int, height_mm: float) -> TableTemplate:
    rows = list(template.rows)
    rows[index] = RowDef(height_mm=max(height_mm, 0.1))
    return replace(template, rows=rows)


def resize_column(template: TableTemplate, index: int, width_fraction: float) -> TableTemplate:
    columns = list(template.columns)
    columns[index] = ColumnDef(width_fraction=max(width_fraction, 1e-6))
    return replace(template, columns=_renormalize_columns(columns))


def find_cell_at(template: TableTemplate, row: int, col: int) -> Optional[CellDef]:
    for cell in template.cells:
        if cell.row <= row < cell.row + cell.row_span and cell.col <= col < cell.col + cell.col_span:
            return cell
    return None


def set_cell(template: TableTemplate, row: int, col: int, **changes) -> TableTemplate:
    cells = []
    updated = False
    for cell in template.cells:
        if not updated and cell.row == row and cell.col == col:
            cells.append(replace(cell, **changes))
            updated = True
        else:
            cells.append(cell)
    return replace(template, cells=cells)


def merge_cells(template: TableTemplate, row: int, col: int, row_span: int, col_span: int) -> TableTemplate:
    row_span = max(1, row_span)
    col_span = max(1, col_span)
    cells = []
    origin_found = False
    for cell in template.cells:
        if cell.row == row and cell.col == col:
            cells.append(replace(cell, row_span=row_span, col_span=col_span))
            origin_found = True
        elif row <= cell.row < row + row_span and col <= cell.col < col + col_span:
            continue
        else:
            cells.append(cell)
    if not origin_found:
        cells.append(CellDef(row=row, col=col, row_span=row_span, col_span=col_span, kind="blank"))
    return replace(template, cells=cells)


def unmerge_cell(template: TableTemplate, row: int, col: int) -> TableTemplate:
    target = find_cell_at(template, row, col)
    if target is None or (target.row_span == 1 and target.col_span == 1):
        return template
    cells = [cell for cell in template.cells if cell is not target]
    cells.append(replace(target, row_span=1, col_span=1))
    for r in range(target.row, target.row + target.row_span):
        for c in range(target.col, target.col + target.col_span):
            if r == target.row and c == target.col:
                continue
            cells.append(CellDef(row=r, col=c, kind="blank"))
    return replace(template, cells=cells)


def add_field(template: TableTemplate, field_def: FieldDef) -> TableTemplate:
    if any(existing.name == field_def.name for existing in template.fields):
        raise ValueError(f"Field '{field_def.name}' already exists.")
    return replace(template, fields=[*template.fields, field_def])


def remove_field(template: TableTemplate, name: str) -> TableTemplate:
    fields = [field_def for field_def in template.fields if field_def.name != name]
    cells = [
        replace(cell, kind="blank", field_name="") if cell.kind == "field" and cell.field_name == name else cell
        for cell in template.cells
    ]
    return replace(template, fields=fields, cells=cells)


def update_field(template: TableTemplate, name: str, **changes) -> TableTemplate:
    fields = [replace(field_def, **changes) if field_def.name == name else field_def for field_def in template.fields]
    return replace(template, fields=fields)


def rename_field(template: TableTemplate, old_name: str, new_name: str) -> TableTemplate:
    if old_name == new_name:
        return template
    if any(existing.name == new_name for existing in template.fields):
        raise ValueError(f"Field '{new_name}' already exists.")
    fields = [replace(f, name=new_name) if f.name == old_name else f for f in template.fields]
    cells = [
        replace(cell, field_name=new_name) if cell.kind == "field" and cell.field_name == old_name else cell
        for cell in template.cells
    ]
    return replace(template, fields=fields, cells=cells)


def default_template() -> TableTemplate:
    columns = [
        ColumnDef(_COL_A_FRACTION),
        ColumnDef(_COL_B_FRACTION),
        ColumnDef(_COL_C_FRACTION),
        ColumnDef(_COL_D_FRACTION),
    ]
    rows = [
        RowDef(_ROW_HEADER_MM),
        RowDef(_ROW_POMIERZYL_MM / 2),
        RowDef(_ROW_POMIERZYL_MM / 2),
        RowDef(_ROW_SPRAWDZIL_MM / 2),
        RowDef(_ROW_SPRAWDZIL_MM / 2),
    ]
    fields = [
        FieldDef(name="sketch_number", label="Szkic nr", scope="sheet", blank_behavior="label_only"),
        FieldDef(name="powiat", label="Powiat", scope="sheet", blank_behavior="hide"),
        FieldDef(name="gmina", label="Gmina", scope="sheet", blank_behavior="hide"),
        FieldDef(name="obreb", label="Obręb", scope="sheet", blank_behavior="hide"),
        FieldDef(name="dz_nr", label="Dz. nr", scope="sheet", blank_behavior="hide"),
    ]
    cells = [
        CellDef(row=0, col=0, kind="static", label="Data", align="center", valign="middle",
                font_size=HEADER_FONT_MM, bold=True),
        CellDef(row=0, col=1, kind="static", label="Nazwisko i imię (wykonawcy)\npodpis", align="center",
                valign="middle", font_size=HEADER_FONT_MM, bold=True),
        CellDef(row=0, col=2, kind="static", label="Adres obiektu :", align="left", valign="middle",
                font_size=HEADER_FONT_MM, bold=True),
        CellDef(row=0, col=3, kind="field", field_name="sketch_number", label="Szkic nr :", show_label=True,
                align="left", valign="middle", font_size=HEADER_FONT_MM, bold=True),
        CellDef(row=1, col=0, row_span=2, kind="static", label="Pomierzył", align="center", valign="middle",
                font_size=BODY_FONT_MM),
        CellDef(row=3, col=0, row_span=2, kind="static", label="Sprawdził", align="center", valign="middle",
                font_size=BODY_FONT_MM),
        CellDef(row=1, col=1, row_span=2, kind="blank"),
        CellDef(row=3, col=1, row_span=2, kind="blank"),
        CellDef(row=1, col=2, kind="field", field_name="powiat", label="powiat", show_label=True,
                align="left", valign="top", font_size=BODY_FONT_MM),
        CellDef(row=2, col=2, kind="field", field_name="gmina", label="gmina", show_label=True,
                align="left", valign="top", font_size=BODY_FONT_MM),
        CellDef(row=3, col=2, kind="field", field_name="obreb", label="obręb", show_label=True,
                align="left", valign="top", font_size=BODY_FONT_MM),
        CellDef(row=4, col=2, kind="field", field_name="dz_nr", label="dz. nr", show_label=True,
                align="left", valign="top", font_size=BODY_FONT_MM),
        CellDef(row=1, col=3, row_span=4, kind="blank"),
    ]
    return TableTemplate(columns=columns, rows=rows, cells=cells, fields=fields)
