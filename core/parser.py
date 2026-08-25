from __future__ import annotations

import os
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple

from core.exceptions import EmptyFileError, FileNotSelectedError, NoValidPointsError
from models.point import Point


class DelimiterMode(Enum):

    AUTO = auto()
    SPACE = auto()
    TAB = auto()


class PointFileParser:

    HEADER_HINTS: Tuple[str, ...] = ("numer", "x", "y")

    def parse_file(self, file_path: str, delimiter_mode: DelimiterMode = DelimiterMode.AUTO) -> Dict[int, Point]:

        if not os.path.isfile(file_path):
            raise FileNotSelectedError("No valid input file selected.")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
        return self.parse_lines(lines, delimiter_mode)

    def parse_lines(self, lines: List[str], delimiter_mode: DelimiterMode = DelimiterMode.AUTO) -> Dict[int, Point]:
        if not lines:
            raise EmptyFileError("Input file is empty.")

        delimiter = self._resolve_delimiter(lines[0], delimiter_mode)
        start_index = 1 if self._looks_like_header(lines[0]) else 0

        data: Dict[int, Point] = {}
        for line in lines[start_index:]:
            parsed = self._parse_row(line, delimiter)
            if parsed is not None:
                number, point = parsed
                data[number] = point

        if not data:
            raise NoValidPointsError("No valid point rows parsed.")
        return data

    @staticmethod
    def detect_delimiter(sample_line: str) -> str:
        return "\t" if "\t" in sample_line else " "

    def _resolve_delimiter(self, sample_line: str, mode: DelimiterMode) -> str:
        if mode is DelimiterMode.SPACE:
            return " "
        if mode is DelimiterMode.TAB:
            return "\t"
        return self.detect_delimiter(sample_line)

    @classmethod
    def _looks_like_header(cls, line: str) -> bool:
        lowered = line.lower()
        return any(hint in lowered for hint in cls.HEADER_HINTS)

    @staticmethod
    def _parse_row(line: str, delimiter: str) -> Optional[Tuple[int, Point]]:
        parts = [part for part in line.replace(",", ".").split(delimiter) if part != ""]
        if len(parts) < 3:
            parts = [part for part in line.replace(",", ".").split() if part != ""]
            if len(parts) < 3:
                return None
        try:
            number = int(parts[0])
        except ValueError:
            return None

        file_x = float(parts[1]) if len(parts) > 1 else 0.0
        file_y = float(parts[2]) if len(parts) > 2 else 0.0
        file_h = float(parts[3]) if len(parts) > 3 else 0.0
        return number, Point(x=file_y, y=file_x, h=file_h)
