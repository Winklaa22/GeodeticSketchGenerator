"""Tests for core.commands.layers (AddLayerCommand, SetLayerColorCommand,
SetLayerVisibleCommand, SetActiveLayerCommand, DeleteLayerCommand,
layers_to_prune)."""
from __future__ import annotations

import pytest

from core.commands.layers import (
    AddLayerCommand,
    DeleteLayerCommand,
    SetActiveLayerCommand,
    SetLayerColorCommand,
    SetLayerVisibleCommand,
    layers_to_prune,
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


def test_add_layer_command_is_a_true_noop_on_an_already_existing_layer(doc: DXFDocument) -> None:
    # e.g. a layer imported from a DXF, or created by an earlier command.
    doc.add_layer("SURVEY", rgb=(9, 9, 9))

    command = AddLayerCommand("SURVEY", rgb=(200, 0, 0))
    command.execute(doc)
    assert doc.get_layer_color("SURVEY") == (9, 9, 9)  # never recolored

    command.undo(doc)
    assert "SURVEY" in doc.layers  # never deleted - this command didn't create it


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


def test_layers_to_prune_keeps_protected_prefixes() -> None:
    imported = ["994-CABLE", "211_MAIN", "219.notes", "SCRAP", "0"]
    result = layers_to_prune(imported, existing_names=imported)
    assert result == ["SCRAP"]


def test_layers_to_prune_ignores_layers_created_after_import() -> None:
    imported = ["SCRAP"]
    existing = ["SCRAP", "NEW_LAYER_ADDED_LATER"]
    # NEW_LAYER_ADDED_LATER isn't in `imported`, so it's never a candidate
    # even though it doesn't start with a protected prefix either.
    result = layers_to_prune(imported, existing_names=existing)
    assert result == ["SCRAP"]


def test_layers_to_prune_skips_layers_already_deleted() -> None:
    imported = ["SCRAP", "ALREADY_GONE"]
    existing = ["SCRAP"]  # ALREADY_GONE no longer exists
    result = layers_to_prune(imported, existing_names=existing)
    assert result == ["SCRAP"]


def test_layers_to_prune_never_includes_layer_zero() -> None:
    result = layers_to_prune(["0"], existing_names=["0"])
    assert result == []


def test_layers_to_prune_returns_nothing_when_all_are_protected() -> None:
    imported = ["994-A", "211-B", "219-C"]
    assert layers_to_prune(imported, existing_names=imported) == []
