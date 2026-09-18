from __future__ import annotations

import pytest

from core.commands.edit import DeleteEntityCommand, DuplicateEntitiesCommand, MoveCommand, RotateCommand, ScaleCommand
from core.commands.history import CommandHistory
from core.commands.multileader import AddMultileaderCommand
from core.commands.text import SetEntityColorCommand
from core.dxf_document import DXFDocument
from core.multileader import MultileaderSpec, leader_points, text_connection
from core.project import ProjectState, load_project, save_project


def _spec(**changes) -> MultileaderSpec:
    values = {
        "tip": (1.0, 2.0),
        "landing": (5.0, 4.0),
        "text_position": (8.0, 4.0),
        "text": "Boundary marker",
        "height": 0.6,
        "layer": "ANNOTATIONS",
    }
    values.update(changes)
    return MultileaderSpec(**values)


def test_straight_multileader_with_landing_creates_atomic_dxf_fallback() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())

    command.execute(doc)

    assert doc.entity_count() == 3
    assert [doc.get_entity(handle).dxftype() for handle in command.handles] == ["LWPOLYLINE", "SOLID", "TEXT"]
    assert doc.multileader_handles(command.handle) == command.handles
    assert doc.multileader_grips(command.handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]
    text = doc.get_entity(command.handle)
    assert text.dxf.layer == "ANNOTATIONS"
    assert text.dxf.text == "Boundary marker"


@pytest.mark.parametrize(
    ("line_type", "arrowhead", "landing_enabled", "expected_types"),
    [
        ("straight", "open", False, ["LINE", "LINE", "LINE", "TEXT"]),
        ("straight", "dot", False, ["LINE", "CIRCLE", "TEXT"]),
        ("spline", "closed", True, ["SPLINE", "SOLID", "TEXT"]),
        ("spline", "open", False, ["SPLINE", "LINE", "LINE", "TEXT"]),
    ],
)
def test_multileader_variants_have_standard_dxf_geometry(
    line_type: str, arrowhead: str, landing_enabled: bool, expected_types: list[str]
) -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(
        _spec(line_type=line_type, arrowhead=arrowhead, landing_enabled=landing_enabled)
    )

    command.execute(doc)

    assert [doc.get_entity(handle).dxftype() for handle in command.handles] == expected_types
    assert doc.get_entity(command.handle).dxf.halign in (0, 2)


def test_multileader_connection_respects_right_text_attachment_gap() -> None:
    spec = _spec(attachment="right", gap=0.25)

    assert text_connection(spec) == pytest.approx((8.25, 4.0))
    assert leader_points(spec)[-1] == pytest.approx((8.25, 4.0))


def test_multileader_undo_redo_and_delete_are_atomic() -> None:
    doc = DXFDocument.new()
    history = CommandHistory()
    command = AddMultileaderCommand(_spec())
    history.execute(command, doc)

    assert history.undo(doc)
    assert doc.entity_count() == 0
    assert history.redo(doc)
    assert doc.entity_count() == 3

    history.execute(DeleteEntityCommand([command.handle]), doc)
    assert doc.entity_count() == 0
    assert history.undo(doc)
    assert doc.entity_count() == 3


def test_moving_the_text_component_moves_the_entire_annotation_and_metadata() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())
    command.execute(doc)
    history = CommandHistory()

    history.execute(MoveCommand([command.handle], 2.0, -3.0), doc)

    assert doc.multileader_grips(command.handle) == [(3.0, -1.0), (7.0, 1.0), (10.0, 1.0)]
    assert len(doc.multileader_handles(command.handle)) == 3
    assert history.undo(doc)
    assert doc.multileader_grips(command.handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]


def test_rotating_and_scaling_any_multileader_component_updates_every_grip() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())
    command.execute(doc)

    RotateCommand([command.handle], 90.0, (0.0, 0.0)).execute(doc)
    assert doc.multileader_grips(command.handle) == [
        pytest.approx((-2.0, 1.0)),
        pytest.approx((-4.0, 5.0)),
        pytest.approx((-4.0, 8.0)),
    ]
    ScaleCommand([command.handle], 2.0, (0.0, 0.0)).execute(doc)
    assert doc.multileader_grips(command.handle) == [
        pytest.approx((-4.0, 2.0)),
        pytest.approx((-8.0, 10.0)),
        pytest.approx((-8.0, 16.0)),
    ]


def test_duplicating_a_multileader_creates_a_separate_annotation_group() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())
    command.execute(doc)
    duplicate = DuplicateEntitiesCommand([command.handle], 10.0, 0.0)

    duplicate.execute(doc)

    assert doc.entity_count() == 6
    assert set(doc.multileader_handles(command.handle)).isdisjoint(duplicate.new_handles)
    assert len(doc.multileader_handles(duplicate.new_handles[-1])) == 3
    assert doc.multileader_grips(command.handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]
    assert doc.multileader_grips(duplicate.new_handles[-1]) == [(11.0, 2.0), (15.0, 4.0), (18.0, 4.0)]


def test_duplicated_multileader_grips_stay_aligned_with_geometry_after_moving_it() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())
    command.execute(doc)
    duplicate = DuplicateEntitiesCommand([command.handle], 10.0, 0.0)
    duplicate.execute(doc)
    copied_text = duplicate.new_handles[-1]

    MoveCommand([copied_text], 0.0, 5.0).execute(doc)

    insert = doc.get_entity(copied_text).dxf.insert
    assert (insert.x, insert.y) == pytest.approx((18.0, 9.0))
    assert doc.multileader_grips(copied_text) == [(11.0, 7.0), (15.0, 9.0), (18.0, 9.0)]
    assert doc.multileader_grips(command.handle) == [(1.0, 2.0), (5.0, 4.0), (8.0, 4.0)]


def test_multileader_text_color_changes_every_annotation_component() -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec())
    command.execute(doc)
    edit = SetEntityColorCommand(command.handle, (20, 30, 40))

    edit.execute(doc)

    assert {doc.get_entity_color(handle) for handle in command.handles} == {(20, 30, 40)}
    edit.undo(doc)
    assert {doc.get_entity_color(handle) for handle in command.handles} == {doc.get_layer_color("ANNOTATIONS")}


def test_multileader_dxf_and_project_round_trip_preserve_grouping(tmp_path) -> None:
    doc = DXFDocument.new()
    command = AddMultileaderCommand(_spec(line_type="spline", arrowhead="open"))
    command.execute(doc)
    content = doc.to_text()

    reopened = DXFDocument.from_text(content)
    assert reopened.entity_count() == 4
    assert len(reopened.multileader_handles(command.handle)) == 4
    assert reopened.multileader_metadata(command.handle)[2].line_type == "spline"

    path = tmp_path / "leader.gsgproj"
    save_project(path, ProjectState(name="Leader", dxf_content=content))
    project = load_project(path)
    project_doc = DXFDocument.from_text(project.dxf_content)
    assert len(project_doc.multileader_handles(command.handle)) == 4
