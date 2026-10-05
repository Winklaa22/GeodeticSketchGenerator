from __future__ import annotations

import math
import os

import ezdxf
import pytest

from core.blocks import add_to_library, file_is_paper_sized, library_blocks, read_block_file
from core.commands.blocks import InsertBlockCommand
from core.dxf_document import DXFDocument

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORTH_ARROW = os.path.join(REPO_ROOT, "assets", "blocks", "Strzałka północy.dxf")


def _write_block_file(path: str, *, units: int = 6, base=(0.0, 0.0, 0.0)) -> str:
    drawing = ezdxf.new("R2013")
    drawing.header["$INSUNITS"] = units
    drawing.header["$INSBASE"] = base
    drawing.modelspace().add_line((0, 0), (0, 10))
    drawing.modelspace().add_circle((0, 10), 1)
    drawing.saveas(path)
    return path


def test_library_lists_dxf_files_by_name_and_ignores_the_rest(tmp_path) -> None:
    _write_block_file(str(tmp_path / "Studzienka.dxf"))
    _write_block_file(str(tmp_path / "Hydrant.DXF"))
    (tmp_path / "notes.txt").write_text("not a block")
    assert [block.name for block in library_blocks([str(tmp_path)])] == ["Hydrant", "Studzienka"]


def test_earlier_library_folder_wins_a_name_clash(tmp_path) -> None:
    builtin, user = tmp_path / "builtin", tmp_path / "user"
    builtin.mkdir()
    user.mkdir()
    shipped = _write_block_file(str(builtin / "Znak.dxf"))
    _write_block_file(str(user / "Znak.dxf"))
    assert [block.path for block in library_blocks([str(builtin), str(user)])] == [shipped]


def test_missing_library_folder_is_just_empty(tmp_path) -> None:
    assert library_blocks([str(tmp_path / "nowhere")]) == []


def test_adding_to_the_library_renames_instead_of_overwriting(tmp_path) -> None:
    source = _write_block_file(str(tmp_path / "Znak.dxf"))
    library = str(tmp_path / "library")
    first = add_to_library(source, library)
    second = add_to_library(source, library)
    assert (first.name, second.name) == ("Znak", "Znak (2)")
    assert os.path.isfile(first.path) and os.path.isfile(second.path)


def test_adding_something_that_is_not_a_drawing_is_refused(tmp_path) -> None:
    junk = tmp_path / "junk.dxf"
    junk.write_bytes(b"\x00\x01definitely not dxf")
    library = tmp_path / "library"
    with pytest.raises(Exception):
        add_to_library(str(junk), str(library))
    assert not list(library.glob("*.dxf"))


def test_importing_a_block_file_keeps_its_base_point_and_units(tmp_path) -> None:
    path = _write_block_file(str(tmp_path / "Znak.dxf"), units=4, base=(0.0, 10.0, 0.0))
    doc = DXFDocument.new()
    doc.import_block("Znak", read_block_file(path))
    block = doc.drawing.blocks["Znak"]
    assert tuple(block.block.dxf.base_point) == (0.0, 10.0, 0.0)
    assert [entity.dxftype() for entity in block] == ["LINE", "CIRCLE"]
    assert doc.block_is_paper_sized("Znak")


def test_an_existing_definition_is_not_replaced(tmp_path) -> None:
    doc = DXFDocument.new()
    existing = doc.drawing.blocks.new(name="Znak")
    existing.add_point((0, 0))
    doc.import_block("Znak", read_block_file(_write_block_file(str(tmp_path / "Znak.dxf"))))
    assert [entity.dxftype() for entity in doc.drawing.blocks["Znak"]] == ["POINT"]


def test_block_names_leave_out_layouts_and_anonymous_blocks() -> None:
    doc = DXFDocument.new()
    doc.drawing.blocks.new(name="PW01")
    doc.drawing.blocks.new_anonymous_block()
    assert doc.block_names() == ["PW01"]


def test_insert_places_one_reference_and_undoes_cleanly(tmp_path) -> None:
    path = _write_block_file(str(tmp_path / "Znak.dxf"))
    doc = DXFDocument.new()
    command = InsertBlockCommand("Znak", (5.0, 6.0), rotation=30.0, scale=2.0, layer="SZKIC", source_path=path)

    command.execute(doc)
    reference = doc.get_entity(command.handle)
    assert reference.dxftype() == "INSERT" and reference.dxf.name == "Znak"
    assert tuple(reference.dxf.insert)[:2] == (5.0, 6.0)
    assert (reference.dxf.rotation, reference.dxf.xscale, reference.dxf.yscale) == (30.0, 2.0, 2.0)
    assert reference.dxf.layer == "SZKIC"

    command.undo(doc)
    assert doc.entity_count() == 0
    assert doc.has_block("Znak"), "the definition stays for other references and a redo"
    command.execute(doc)
    assert doc.get_entity(command.handle) is reference and doc.entity_count() == 1


def test_a_placed_block_moves_rotates_and_survives_save_and_reopen(tmp_path) -> None:
    doc = DXFDocument.new()
    command = InsertBlockCommand("Znak", (0.0, 0.0), source_path=_write_block_file(str(tmp_path / "Znak.dxf")))
    command.execute(doc)
    doc.translate_entities([command.handle], 10.0, 0.0)
    doc.rotate_entities([command.handle], 90.0, (10.0, 0.0))
    reference = doc.get_entity(command.handle)
    assert tuple(reference.dxf.insert)[:2] == pytest.approx((10.0, 0.0))
    assert reference.dxf.rotation == pytest.approx(90.0)

    reopened = DXFDocument.from_text(doc.to_text())
    assert reopened.block_names() == ["Znak"]
    assert reopened.get_entity(command.handle).dxf.name == "Znak"


def test_the_north_arrow_ships_upright_and_paper_sized() -> None:
    drawing = read_block_file(NORTH_ARROW)
    assert file_is_paper_sized(drawing)
    assert tuple(drawing.header["$INSBASE"]) == (0.0, 0.0, 0.0)
    axis, arrowhead, letter = list(drawing.modelspace())

    # The axis runs straight up through the base point and on down through the N.
    top, bottom = (axis.dxf.start.x, axis.dxf.start.y), (axis.dxf.end.x, axis.dxf.end.y)
    assert top[0] == bottom[0] == 0.0 and top[1] > 0.0 > bottom[1]

    # A half arrowhead on the left, closed by a base square to the axis that runs past it.
    tip, barb, base_end = [(p[0], p[1]) for p in arrowhead.get_points("xy")]
    assert tip == top
    assert barb[0] < 0.0 < base_end[0] and barb[1] == base_end[1] == 0.0
    assert math.degrees(math.atan2(-barb[0], tip[1] - barb[1])) == pytest.approx(7.18, abs=0.05)

    # The N stands below the base, straddling the axis, legs parallel to it.
    left_bottom, left_top, right_bottom, right_top = [(p[0], p[1]) for p in letter.get_points("xy")]
    assert left_bottom[0] == left_top[0] < 0.0 < right_bottom[0] == right_top[0]
    assert left_top[1] == right_top[1] < 0.0 and left_bottom[1] == right_bottom[1] > bottom[1]
