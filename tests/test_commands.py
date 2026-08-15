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
from core.commands.edit import DeleteEntityCommand, MoveCommand
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
