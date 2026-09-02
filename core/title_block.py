from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Dict, List, Tuple

ROW_HEADER_MM = 8.5
ROW_POMIERZYL_MM = 15.0
ROW_SPRAWDZIL_MM = 9.0
TABLE_HEIGHT_MM = ROW_HEADER_MM + ROW_POMIERZYL_MM + ROW_SPRAWDZIL_MM

COL_A_FRACTION = 0.10
COL_B_FRACTION = 0.38
COL_C_FRACTION = 0.24
COL_D_FRACTION = 0.28

HEADER_FONT_MM = 2.0
BODY_FONT_MM = 2.4
LICENSE_FONT_MM = 1.8
BORDER_WIDTH_MM = 0.35
CELL_PADDING_MM = 1.5

_LABEL_DATA = "Data"
_LABEL_NAME = "Nazwisko i imię (wykonawcy)\npodpis"
_LABEL_ADDRESS = "Adres obiektu :"
_LABEL_SKETCH = "Szkic nr :"
_LABEL_POMIERZYL = "Pomierzył"
_LABEL_SPRAWDZIL = "Sprawdził"


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
class TitleBlockProfile:
    surveyor_title: str = ""
    surveyor_name: str = ""
    license_text: str = ""


@dataclass(frozen=True)
class SheetTitleBlockFields:
    powiat: str = ""
    gmina: str = ""
    obreb: str = ""
    dz_nr: str = ""
    sketch_number: str = ""


@dataclass(frozen=True)
class Cell:
    rect: Rect
    kind: str = "text"
    label: str = ""
    field: str = ""
    align: str = "left"
    valign: str = "top"
    font_size: float = BODY_FONT_MM
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class ResolvedCell(Cell):
    text: str = ""


def _join_lines(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


_RESOLVERS: Dict[str, Callable[[TitleBlockProfile, SheetTitleBlockFields], str]] = {
    "address_block": lambda profile, fields: _join_lines(
        f"powiat {fields.powiat}" if fields.powiat else "",
        f"gmina {fields.gmina}" if fields.gmina else "",
        f"obręb {fields.obreb}" if fields.obreb else "",
        f"dz. nr {fields.dz_nr}" if fields.dz_nr else "",
    ),
}


def cell_layout(table_width: float, scale: float = 1.0) -> List[Cell]:
    a = table_width * COL_A_FRACTION
    b = table_width * COL_B_FRACTION
    c = table_width * COL_C_FRACTION
    d = table_width * COL_D_FRACTION
    x_a, x_b, x_c, x_d = 0.0, a, a + b, a + b + c

    header_h = ROW_HEADER_MM * scale
    pom_h = ROW_POMIERZYL_MM * scale
    spr_h = ROW_SPRAWDZIL_MM * scale
    body_h = pom_h + spr_h
    y_header, y_pom, y_spr = 0.0, header_h, header_h + pom_h

    header_font = HEADER_FONT_MM * scale
    body_font = BODY_FONT_MM * scale
    license_font = LICENSE_FONT_MM * scale

    return [
        Cell(Rect(x_a, y_header, a, header_h), label=_LABEL_DATA, align="center", valign="middle",
             font_size=header_font, bold=True),
        Cell(Rect(x_b, y_header, b, header_h), label=_LABEL_NAME, align="center", valign="middle",
             font_size=header_font, bold=True),
        Cell(Rect(x_c, y_header, c, header_h), label=_LABEL_ADDRESS, align="left", valign="middle",
             font_size=header_font, bold=True),
        Cell(Rect(x_d, y_header, d, header_h), label=_LABEL_SKETCH, field="sketch_number",
             align="left", valign="middle", font_size=header_font, bold=True),
        Cell(Rect(x_a, y_pom, a, pom_h), label=_LABEL_POMIERZYL, align="center", valign="middle",
             font_size=body_font),
        Cell(Rect(x_a, y_spr, a, spr_h), label=_LABEL_SPRAWDZIL, align="center", valign="middle",
             font_size=body_font),
        Cell(Rect(x_b, y_pom, b, pom_h), field="surveyor_block", align="left", valign="top",
             font_size=license_font),
        Cell(Rect(x_b, y_spr, b, spr_h), kind="blank"),
        Cell(Rect(x_c, y_pom, c, body_h), field="address_block", align="left", valign="top",
             font_size=body_font),
        Cell(Rect(x_d, y_pom, d, body_h), kind="blank"),
    ]


def resolve_cells(
    cells: List[Cell], profile: TitleBlockProfile, fields: SheetTitleBlockFields
) -> List[ResolvedCell]:
    resolved = []
    for cell in cells:
        if cell.kind == "blank":
            text = ""
        elif cell.field == "surveyor_block":
            text = ""
        elif cell.field == "sketch_number":
            value = fields.sketch_number
            text = f"{cell.label} {value}" if value else cell.label
        elif cell.field and cell.field in _RESOLVERS:
            text = _RESOLVERS[cell.field](profile, fields)
        else:
            text = cell.label
        resolved.append(
            ResolvedCell(
                rect=cell.rect, kind=cell.kind, label=cell.label, field=cell.field,
                align=cell.align, valign=cell.valign, font_size=cell.font_size,
                bold=cell.bold, italic=cell.italic, text=text,
            )
        )
    return resolved


def title_block_layout(
    table_rect: Rect,
    profile: TitleBlockProfile,
    fields: SheetTitleBlockFields,
    scale: float = 1.0,
) -> List[ResolvedCell]:
    cells = resolve_cells(cell_layout(table_rect.w, scale), profile, fields)
    return [
        replace(cell, rect=Rect(cell.rect.x + table_rect.x, cell.rect.y + table_rect.y, cell.rect.w, cell.rect.h))
        for cell in cells
    ]


def split_printable_rect(printable: Rect, table_height: float) -> Tuple[Rect, Rect]:
    height = max(printable.h - table_height, 0.0)
    map_rect = Rect(printable.x, printable.y, printable.w, height)
    table_rect = Rect(printable.x, map_rect.bottom(), printable.w, printable.h - height)
    return map_rect, table_rect
