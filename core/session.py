from __future__ import annotations

import os
from enum import Enum
from typing import Dict, Optional

from core.exceptions import AppError
from core.formatting import format_file_size
from core.parser import DelimiterMode, PointFileParser
from models.point import Point


class AppState(Enum):

    EMPTY = "empty"
    READY = "ready"
    APPLIED = "applied"
    ERROR = "error"


class EditorSession:

    def __init__(self, parser: Optional[PointFileParser] = None) -> None:
        self.parser = parser if parser is not None else PointFileParser()
        self.file_path: str = ""
        self.file_size_text: str = ""
        self.data: Dict[int, Point] = {}
        self.dxf_path: str = ""
        self.has_applied: bool = False
        self.last_error: Optional[str] = None

    @property
    def state(self) -> AppState:
        if self.last_error:
            return AppState.ERROR
        if not self.file_path:
            return AppState.EMPTY
        if self.has_applied:
            return AppState.APPLIED
        return AppState.READY

    @property
    def has_file(self) -> bool:
        return bool(self.file_path)

    @property
    def file_name(self) -> str:
        return os.path.basename(self.file_path)

    @property
    def point_count(self) -> int:
        return len(self.data)

    def load_points(self, file_path: str, delimiter_mode: DelimiterMode) -> None:
        self.file_path = file_path
        self.file_size_text = format_file_size(file_path)
        self.reparse_points(delimiter_mode)

    def reparse_points(self, delimiter_mode: DelimiterMode) -> None:
        self.invalidate()
        try:
            self.data = self.parser.parse_file(self.file_path, delimiter_mode)
            self.last_error = None
        except AppError as exc:
            self.data = {}
            self.last_error = str(exc)

    def set_dxf_path(self, path: str) -> None:
        self.dxf_path = path
        self.invalidate()

    def invalidate(self) -> None:
        self.has_applied = False

    def fail(self, message: str) -> None:
        self.last_error = message
        self.has_applied = False

    def mark_applied(self) -> None:
        self.last_error = None
        self.has_applied = True
