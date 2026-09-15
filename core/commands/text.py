from __future__ import annotations

from typing import List, Optional, Tuple

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

    def __init__(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self._handle = handle
        self._rgb = rgb
        self._previous: List[Tuple[str, Tuple[int, int, int]]] = []

    def execute(self, doc: DXFDocument) -> None:
        handles = doc.expand_annotation_handles([self._handle])
        self._previous = [(handle, doc.get_entity_color(handle)) for handle in handles]
        for handle in handles:
            doc.set_entity_color(handle, self._rgb)

    def undo(self, doc: DXFDocument) -> None:
        for handle, color in self._previous:
            doc.set_entity_color(handle, color)
