from __future__ import annotations

from typing import Iterable, List, Optional, Tuple

from core.commands.edit import DeleteEntityCommand
from core.dxf_document import DXFDocument

PROTECTED_LAYER_PREFIXES: Tuple[str, ...] = ("994", "211", "219")


def layers_to_prune(imported_names: Iterable[str], existing_names: Iterable[str]) -> List[str]:
    existing = set(existing_names)
    return sorted(
        name
        for name in imported_names
        if name in existing and name != "0" and not name.startswith(PROTECTED_LAYER_PREFIXES)
    )


class AddLayerCommand:

    def __init__(self, name: str, rgb: Optional[Tuple[int, int, int]] = None) -> None:
        self._name = name
        self._rgb = rgb
        self._created = False

    def execute(self, doc: DXFDocument) -> None:
        self._created = self._name not in doc.layers
        doc.add_layer(self._name, self._rgb)

    def undo(self, doc: DXFDocument) -> None:
        if self._created:
            doc.remove_layer(self._name)


class SetLayerColorCommand:
    def __init__(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self._name = name
        self._rgb = rgb
        self._previous: Optional[Tuple[int, int, int]] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_layer_color(self._name)
        doc.set_layer_color(self._name, self._rgb)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_layer_color(self._name, self._previous)


class SetLayerVisibleCommand:
    def __init__(self, name: str, visible: bool) -> None:
        self._name = name
        self._visible = visible

    def execute(self, doc: DXFDocument) -> None:
        doc.set_layer_visible(self._name, self._visible)

    def undo(self, doc: DXFDocument) -> None:
        doc.set_layer_visible(self._name, not self._visible)


class SetActiveLayerCommand:
    def __init__(self, name: str) -> None:
        self._name = name
        self._previous: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.active_layer
        doc.set_active_layer(self._name)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_active_layer(self._previous)


class DeleteLayerCommand:

    def __init__(self, name: str) -> None:
        self._name = name
        self._delete_entities: Optional[DeleteEntityCommand] = None
        self._rgb: Optional[Tuple[int, int, int]] = None
        self._was_active = False

    def execute(self, doc: DXFDocument) -> None:
        handles: List[str] = [
            entity.dxf.handle for entity in doc.modelspace if entity.dxf.layer == self._name
        ]
        self._delete_entities = DeleteEntityCommand(handles)
        self._delete_entities.execute(doc)
        self._rgb = doc.get_layer_color(self._name)
        self._was_active = doc.active_layer == self._name
        doc.remove_layer(self._name)

    def undo(self, doc: DXFDocument) -> None:
        doc.add_layer(self._name, self._rgb)
        if self._delete_entities is not None:
            self._delete_entities.undo(doc)
        if self._was_active:
            doc.set_active_layer(self._name)
