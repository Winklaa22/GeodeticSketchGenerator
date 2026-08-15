"""Tests for core.commands.layers (AddLayerCommand, SetLayerColorCommand,
SetLayerVisibleCommand, SetActiveLayerCommand, DeleteLayerCommand)."""
from __future__ import annotations

import pytest

from core.commands.layers import (
    AddLayerCommand,
    DeleteLayerCommand,
    SetActiveLayerCommand,
    SetLayerColorCommand,
    SetLayerVisibleCommand,
)
from core.dxf_document import DXFDocument


@pytest.fixture
def doc() -> DXFDocument:
    return DXFDocument.new()


def test_add_layer_command_execute_and_undo(doc: DXFDocument) -> None:
    command = AddLayerCommand("SURVEY", rgb=(10, 20, 30))
    command.execute(doc)
    assert "SURVEY" in doc.layers
    assert doc.get_layer_color("SURVEY") == (10, 20, 30)
    command.undo(doc)
    assert "SURVEY" not in doc.layers


def test_set_layer_color_command_execute_and_undo(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(1, 1, 1))
    command = SetLayerColorCommand("SURVEY", (200, 100, 50))
    command.execute(doc)
    assert doc.get_layer_color("SURVEY") == (200, 100, 50)
    command.undo(doc)
    assert doc.get_layer_color("SURVEY") == (1, 1, 1)


def test_set_layer_visible_command_execute_and_undo(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    command = SetLayerVisibleCommand("SURVEY", False)
    command.execute(doc)
    assert doc.is_layer_visible("SURVEY") is False
    command.undo(doc)
    assert doc.is_layer_visible("SURVEY") is True


def test_set_active_layer_command_execute_and_undo(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    assert doc.active_layer == "0"
    command = SetActiveLayerCommand("SURVEY")
    command.execute(doc)
    assert doc.active_layer == "SURVEY"
    command.undo(doc)
    assert doc.active_layer == "0"


def test_delete_layer_command_removes_layer_and_its_entities(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(9, 9, 9))
    doc.add_point((0.0, 0.0), layer="SURVEY")
    doc.add_point((1.0, 1.0), layer="SURVEY")
    doc.add_point((2.0, 2.0), layer="0")  # unrelated, must survive

    command = DeleteLayerCommand("SURVEY")
    command.execute(doc)

    assert "SURVEY" not in doc.layers
    assert doc.entity_count() == 1  # only the layer-0 point remains


def test_delete_layer_command_undo_restores_layer_entities_and_color(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY", rgb=(9, 9, 9))
    doc.add_point((0.0, 0.0), layer="SURVEY")
    doc.add_point((1.0, 1.0), layer="SURVEY")

    command = DeleteLayerCommand("SURVEY")
    command.execute(doc)
    command.undo(doc)

    assert "SURVEY" in doc.layers
    assert doc.get_layer_color("SURVEY") == (9, 9, 9)
    assert doc.entity_count() == 2
    assert all(e.dxf.layer == "SURVEY" for e in doc.modelspace)


def test_delete_layer_command_restores_active_layer_status_on_undo(doc: DXFDocument) -> None:
    doc.add_layer("SURVEY")
    doc.set_active_layer("SURVEY")

    command = DeleteLayerCommand("SURVEY")
    command.execute(doc)
    assert doc.active_layer == "0"  # reset when the active layer got deleted

    command.undo(doc)
    assert doc.active_layer == "SURVEY"


def test_delete_layer_command_refuses_layer_zero(doc: DXFDocument) -> None:
    with pytest.raises(ValueError):
        DeleteLayerCommand("0").execute(doc)
