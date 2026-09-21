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


class SetTextFontCommand:
    def __init__(self, handle: str, font_id: str) -> None:
        self._handle = handle
        self._font_id = font_id
        self._previous: Optional[str] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_font(self._handle)
        doc.set_text_font(self._handle, self._font_id)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_text_font(self._handle, self._previous)


class SetTextItalicCommand:
    def __init__(self, handle: str, italic: bool) -> None:
        self._handle = handle
        self._italic = italic
        self._previous: Optional[bool] = None

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_italic(self._handle)
        doc.set_text_italic(self._handle, self._italic)

    def undo(self, doc: DXFDocument) -> None:
        if self._previous is not None:
            doc.set_text_italic(self._handle, self._previous)


class SetTextLineweightCommand:
    def __init__(self, handle: str, lineweight_mm: Optional[float]) -> None:
        self._handle = handle
        self._lineweight_mm = lineweight_mm
        self._previous: Optional[float] = None
        self._has_previous = False

    def execute(self, doc: DXFDocument) -> None:
        self._previous = doc.get_text_lineweight_mm(self._handle)
        self._has_previous = True
        doc.set_text_lineweight_mm(self._handle, self._lineweight_mm)

    def undo(self, doc: DXFDocument) -> None:
        if self._has_previous:
            doc.set_text_lineweight_mm(self._handle, self._previous)


class ApplyFontToAllTextCommand:
    def __init__(self, font_id: str, italic: bool, lineweight_mm: Optional[float]) -> None:
        self._font_id = font_id
        self._italic = italic
        self._lineweight_mm = lineweight_mm
        self._previous: List[Tuple[str, str, bool, Optional[float]]] = []

    def execute(self, doc: DXFDocument) -> None:
        handles = doc.all_text_handles()
        self._previous = [
            (handle, doc.get_text_font(handle), doc.get_text_italic(handle), doc.get_text_lineweight_mm(handle))
            for handle in handles
        ]
        for handle in handles:
            doc.set_text_font(handle, self._font_id)
            doc.set_text_italic(handle, self._italic)
            doc.set_text_lineweight_mm(handle, self._lineweight_mm)

    def undo(self, doc: DXFDocument) -> None:
        for handle, font_id, italic, lineweight_mm in self._previous:
            doc.set_text_font(handle, font_id)
            doc.set_text_italic(handle, italic)
            doc.set_text_lineweight_mm(handle, lineweight_mm)


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
