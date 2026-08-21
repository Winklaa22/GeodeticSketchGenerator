"""TEXT entity property commands — content/height/rotation/color, edited via
the floating text-options toolbar (see ui/dxf_viewer.py's TextOptionsBar)."""
from __future__ import annotations

from typing import Optional, Tuple

from core.dxf_document import DXFDocument


class SetTextContentCommand:
    def __init__(self, handle: str, text: str) -> None:
        self._handle = handle
        self._text = text
        self._previous: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_content(self._handle)
        doc.set_text_content(self._handle, self._text)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_text_content(self._handle, self._previous)


class SetTextHeightCommand:
    def __init__(self, handle: str, height: float) -> None:
        self._handle = handle
        self._height = height
        self._previous: Optional[float] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_height(self._handle)
        doc.set_text_height(self._handle, self._height)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_text_height(self._handle, self._previous)


class SetTextRotationCommand:
    def __init__(self, handle: str, rotation: float) -> None:
        self._handle = handle
        self._rotation = rotation
        self._previous: Optional[float] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_rotation(self._handle)
        doc.set_text_rotation(self._handle, self._rotation)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_text_rotation(self._handle, self._previous)


class SetEntityColorCommand:
    """Same idea as `core.commands.layers.SetLayerColorCommand`, but for one
    entity's own color override rather than a whole layer's."""

    def __init__(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self._handle = handle
        self._rgb = rgb
        self._previous: Optional[Tuple[int, int, int]] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_entity_color(self._handle)
        doc.set_entity_color(self._handle, self._rgb)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_entity_color(self._handle, self._previous)
