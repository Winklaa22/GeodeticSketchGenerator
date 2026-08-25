"""Tests for core.commands (Command implementations, CommandHistory, CompositeCommand)."""
from __future__ import annotations

import pytest

from core.commands.composite import CompositeCommand
from core.commands.draw import (
    AddCircleCommand,
    AddLineCommand,
    AddPointCommand,
    AddPolyline2DCommand,
    AddPolyline3DCommand,
    AddTextCommand,
)
from core.commands.edit import (
    DeleteEntityCommand,
    DuplicateEntitiesCommand,
    MoveCommand,
    RotateCommand,
    ScaleCommand,
)
from core.commands.history import CommandHistory
from core.dxf_document import DXFDocument


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


@pytest.fixture
def history() -> CommandHistory:
    return CommandHistory()


# ----------------------------------------------------------------------
# Draw commands
# ----------------------------------------------------------------------
def test_add_point_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddPointCommand((1.0, 1.0))
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_add_line_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddLineCommand((0.0, 0.0), (5.0, 5.0), layer="ROADS")
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_add_circle_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddCircleCommand((0.0, 0.0), radius=3.0)
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_add_text_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddTextCommand("42", (0.0, 0.0, 1.0), height=0.6, layer="LABELS", rotation=90.0)
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_add_polyline2d_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddPolyline2DCommand([(0.0, 0.0), (1.0, 1.0), (2.0, 0.0)])
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_add_polyline3d_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddPolyline3DCommand([(0.0, 0.0, 1.0), (1.0, 1.0, 2.0)], closed=True)
    command.execute(doc)
    assert doc.entity_count() == 1
    command.undo(doc)
    assert doc.entity_count() == 0


def test_undo_before_execute_is_a_safe_no_op(doc: DXFDocument) -> None:
    command = AddPointCommand((0.0, 0.0))
    command.undo(doc)  # never executed — must not raise
    assert doc.entity_count() == 0


def test_add_point_command_redo_relinks_the_same_handle(doc: DXFDocument) -> None:
    """A second execute() (a redo) must reuse the entity/handle the first
    one created, not fabricate a new one — see DXFDocument.relink_entity."""
    command = AddPointCommand((1.0, 1.0))
    command.execute(doc)
    first_handle = command._handle
    command.undo(doc)
    command.execute(doc)  # redo
    assert command._handle == first_handle
    assert doc.entity_count() == 1


# ----------------------------------------------------------------------
# Edit commands
# ----------------------------------------------------------------------
def test_delete_entity_command_execute_and_undo(doc: DXFDocument) -> None:
    handle = doc.add_point((0.0, 0.0))
    command = DeleteEntityCommand([handle])
    command.execute(doc)
    assert doc.entity_count() == 0
    command.undo(doc)
    assert doc.entity_count() == 1
    assert doc.get_entity(handle) is not None


def test_delete_entity_command_handles_multiple_handles(doc: DXFDocument) -> None:
    handles = [doc.add_point((float(n), 0.0)) for n in range(3)]
    command = DeleteEntityCommand(handles)
    command.execute(doc)
    assert doc.entity_count() == 0
    command.undo(doc)
    assert doc.entity_count() == 3


def test_move_command_execute_and_undo(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (1.0, 1.0))
    command = MoveCommand([handle], dx=5.0, dy=-3.0)
    command.execute(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == (5.0, -3.0)
    assert tuple(entity.dxf.end)[:2] == (6.0, -2.0)
    command.undo(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == (0.0, 0.0)
    assert tuple(entity.dxf.end)[:2] == (1.0, 1.0)


def test_move_command_moves_multiple_handles_together(doc: DXFDocument) -> None:
    handles = [doc.add_point((float(n), 0.0)) for n in range(3)]
    command = MoveCommand(handles, dx=1.0, dy=1.0)
    command.execute(doc)
    for n, handle in enumerate(handles):
        assert tuple(doc.get_entity(handle).dxf.location)[:2] == (float(n) + 1.0, 1.0)


def test_duplicate_entities_command_offsets_the_copy(doc: DXFDocument) -> None:
    handle = doc.add_line((0.0, 0.0), (10.0, 0.0))
    command = DuplicateEntitiesCommand([handle], dx=2.0, dy=3.0)
    command.execute(doc)
    assert doc.entity_count() == 2
    [new_handle] = command.new_handles
    assert new_handle != handle  # a real second entity, not the same one moved
    copy = doc.get_entity(new_handle)
    assert tuple(copy.dxf.start)[:2] == (2.0, 3.0)
    assert tuple(copy.dxf.end)[:2] == (12.0, 3.0)
    original = doc.get_entity(handle)
    assert tuple(original.dxf.start)[:2] == (0.0, 0.0)  # original is untouched


def test_duplicate_entities_command_execute_and_undo(doc: DXFDocument) -> None:
    handles = [doc.add_point((float(n), 0.0)) for n in range(3)]
    command = DuplicateEntitiesCommand(handles, dx=1.0, dy=1.0)
    command.execute(doc)
    assert doc.entity_count() == 6
    command.undo(doc)
    assert doc.entity_count() == 3


def test_duplicate_entities_command_redo_relinks_the_same_new_handles(doc: DXFDocument) -> None:
    handle = doc.add_point((0.0, 0.0))
    command = DuplicateEntitiesCommand([handle], dx=1.0, dy=1.0)
    command.execute(doc)
    first_new_handles = list(command.new_handles)
    command.undo(doc)
    command.execute(doc)  # redo
    assert command.new_handles == first_new_handles
    assert doc.entity_count() == 2


def test_rotate_command_execute_and_undo(doc: DXFDocument) -> None:
    handle = doc.add_line((10.0, 0.0), (20.0, 0.0))
    command = RotateCommand([handle], angle=90.0, center=(0.0, 0.0))
    command.execute(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == pytest.approx((0.0, 10.0), abs=1e-9)
    assert tuple(entity.dxf.end)[:2] == pytest.approx((0.0, 20.0), abs=1e-9)
    command.undo(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == pytest.approx((10.0, 0.0), abs=1e-9)
    assert tuple(entity.dxf.end)[:2] == pytest.approx((20.0, 0.0), abs=1e-9)


def test_rotate_command_rotates_multiple_handles_together(doc: DXFDocument) -> None:
    handles = [doc.add_point((1.0, 0.0)), doc.add_point((2.0, 0.0))]
    command = RotateCommand(handles, angle=180.0, center=(0.0, 0.0))
    command.execute(doc)
    assert tuple(doc.get_entity(handles[0]).dxf.location)[:2] == pytest.approx((-1.0, 0.0), abs=1e-9)
    assert tuple(doc.get_entity(handles[1]).dxf.location)[:2] == pytest.approx((-2.0, 0.0), abs=1e-9)


def test_scale_command_execute_and_undo(doc: DXFDocument) -> None:
    handle = doc.add_line((10.0, 0.0), (20.0, 0.0))
    command = ScaleCommand([handle], factor=2.0, center=(10.0, 0.0))
    command.execute(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == pytest.approx((10.0, 0.0), abs=1e-9)
    assert tuple(entity.dxf.end)[:2] == pytest.approx((30.0, 0.0), abs=1e-9)
    command.undo(doc)
    entity = doc.get_entity(handle)
    assert tuple(entity.dxf.start)[:2] == pytest.approx((10.0, 0.0), abs=1e-9)
    assert tuple(entity.dxf.end)[:2] == pytest.approx((20.0, 0.0), abs=1e-9)


def test_scale_command_scales_multiple_handles_together(doc: DXFDocument) -> None:
    handles = [doc.add_point((1.0, 0.0)), doc.add_point((2.0, 0.0))]
    command = ScaleCommand(handles, factor=3.0, center=(0.0, 0.0))
    command.execute(doc)
    assert tuple(doc.get_entity(handles[0]).dxf.location)[:2] == pytest.approx((3.0, 0.0), abs=1e-9)
    assert tuple(doc.get_entity(handles[1]).dxf.location)[:2] == pytest.approx((6.0, 0.0), abs=1e-9)


def test_scale_command_leaves_z_untouched(doc: DXFDocument) -> None:
    handle = doc.add_point((10.0, 0.0, 5.0))
    command = ScaleCommand([handle], factor=2.0, center=(0.0, 0.0))
    command.execute(doc)
    assert doc.get_entity(handle).dxf.location.z == pytest.approx(5.0, abs=1e-9)


# ----------------------------------------------------------------------
# CommandHistory
# ----------------------------------------------------------------------
def test_history_execute_runs_command_and_tracks_undo(doc: DXFDocument, history: CommandHistory) -> None:
    history.execute(AddPointCommand((0.0, 0.0)), doc)
    assert doc.entity_count() == 1
    assert history.can_undo()
    assert not history.can_redo()


def test_history_undo_then_redo_round_trips(doc: DXFDocument, history: CommandHistory) -> None:
    history.execute(AddPointCommand((0.0, 0.0)), doc)
    assert history.undo(doc) is True
    assert doc.entity_count() == 0
    assert history.can_redo()
    assert history.redo(doc) is True
    assert doc.entity_count() == 1


def test_history_redoing_a_create_then_a_delete_of_it_does_not_crash(
    doc: DXFDocument, history: CommandHistory
) -> None:
    """Regression test: undoing a create and the delete that followed it (in
    that order — the delete first, then the create), then redoing both back
    (the create first, then the delete) used to crash — DeleteEntityCommand
    still names the handle from *before* the create's redo, which (without
    DXFDocument.relink_entity/Add*Command reusing that same handle) would
    otherwise have been a fresh one, leaving DeleteEntityCommand pointed at
    an entity ezdxf had already dropped from the model space."""
    add = AddPointCommand((0.0, 0.0))
    history.execute(add, doc)
    handle = add._handle
    history.execute(DeleteEntityCommand([handle]), doc)
    assert doc.entity_count() == 0

    assert history.undo(doc) is True  # undoes the delete
    assert history.undo(doc) is True  # undoes the create
    assert doc.entity_count() == 0

    assert history.redo(doc) is True  # redoes the create
    assert history.redo(doc) is True  # redoes the delete - must not raise
    assert doc.entity_count() == 0


def test_history_redoing_a_duplicate_then_a_delete_of_it_does_not_crash(
    doc: DXFDocument, history: CommandHistory
) -> None:
    """Same regression as above, for DuplicateEntitiesCommand (Ctrl+D/Ctrl+V)
    instead of an Add*Command — this is the exact sequence a user hits by
    duplicating something, deleting the duplicate, then undoing/redoing
    past that point."""
    source = doc.add_point((0.0, 0.0))
    duplicate = DuplicateEntitiesCommand([source], dx=1.0, dy=1.0)
    history.execute(duplicate, doc)
    [new_handle] = duplicate.new_handles
    history.execute(DeleteEntityCommand([new_handle]), doc)
    assert doc.entity_count() == 1  # just the original

    assert history.undo(doc) is True  # undoes the delete
    assert history.undo(doc) is True  # undoes the duplicate
    assert doc.entity_count() == 1

    assert history.redo(doc) is True  # redoes the duplicate
    assert history.redo(doc) is True  # redoes the delete - must not raise
    assert doc.entity_count() == 1


def test_history_undo_on_empty_stack_returns_false(doc: DXFDocument, history: CommandHistory) -> None:
    assert history.undo(doc) is False


def test_history_redo_on_empty_stack_returns_false(doc: DXFDocument, history: CommandHistory) -> None:
    assert history.redo(doc) is False


def test_history_new_execute_clears_redo_stack(doc: DXFDocument, history: CommandHistory) -> None:
    history.execute(AddPointCommand((0.0, 0.0)), doc)
    history.undo(doc)
    assert history.can_redo()
    history.execute(AddPointCommand((1.0, 1.0)), doc)
    assert not history.can_redo()
    assert doc.entity_count() == 1


def test_history_respects_max_depth(doc: DXFDocument) -> None:
    history = CommandHistory(max_depth=2)
    for n in range(5):
        history.execute(AddPointCommand((float(n), 0.0)), doc)
    assert doc.entity_count() == 5
    undone = 0
    while history.undo(doc):
        undone += 1
    assert undone == 2  # only the last 2 commands are still undoable
    assert doc.entity_count() == 3


def test_history_clear_drops_both_stacks(doc: DXFDocument, history: CommandHistory) -> None:
    history.execute(AddPointCommand((0.0, 0.0)), doc)
    history.undo(doc)
    history.clear()
    assert not history.can_undo()
    assert not history.can_redo()


# ----------------------------------------------------------------------
# CompositeCommand
# ----------------------------------------------------------------------
def test_composite_command_executes_all_sub_commands(doc: DXFDocument) -> None:
    composite = CompositeCommand(
        [AddPointCommand((0.0, 0.0)), AddLineCommand((0.0, 0.0), (1.0, 1.0)), AddCircleCommand((0.0, 0.0), 1.0)]
    )
    composite.execute(doc)
    assert doc.entity_count() == 3


def test_composite_command_undo_reverses_all_sub_commands(doc: DXFDocument) -> None:
    composite = CompositeCommand([AddPointCommand((0.0, 0.0)), AddLineCommand((0.0, 0.0), (1.0, 1.0))])
    composite.execute(doc)
    composite.undo(doc)
    assert doc.entity_count() == 0


def test_composite_command_works_through_history(doc: DXFDocument, history: CommandHistory) -> None:
    composite = CompositeCommand([AddPointCommand((0.0, 0.0)), AddPointCommand((1.0, 1.0))])
    history.execute(composite, doc)
    assert doc.entity_count() == 2
    history.undo(doc)
    assert doc.entity_count() == 0
    history.redo(doc)
    assert doc.entity_count() == 2
