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

        return self.parse_lines(self._read_lines(file_path), delimiter_mode)

    def parse_file_with_quantum(
        self, file_path: str, delimiter_mode: DelimiterMode = DelimiterMode.AUTO
    ) -> Tuple[Dict[int, Point], float]:
        lines = self._read_lines(file_path)
        return self.parse_lines(lines, delimiter_mode), self.estimate_quantum(lines, delimiter_mode)

    @staticmethod
    def _read_lines(file_path: str) -> List[str]:
        if not os.path.isfile(file_path):
            raise FileNotSelectedError("No valid input file selected.")
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return [line.strip() for line in f.readlines() if line.strip()]

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

    def estimate_quantum(self, lines: List[str], delimiter_mode: DelimiterMode = DelimiterMode.AUTO) -> float:
        if not lines:
            raise EmptyFileError("Input file is empty.")

        delimiter = self._resolve_delimiter(lines[0], delimiter_mode)
        start_index = 1 if self._looks_like_header(lines[0]) else 0

        max_decimals = 0
        found_row = False
        for line in lines[start_index:]:
            tokens = self._tokenize_row(line, delimiter)
            if tokens is None:
                continue
            found_row = True
            for token in tokens[1:3]:
                max_decimals = max(max_decimals, self._decimal_places(token))

        if not found_row:
            raise NoValidPointsError("No valid point rows parsed.")

        # A file with no decimal point anywhere records no finer resolution
        # than one whole coordinate unit; q = 1.0 falls out of the same
        # formula rather than being a separately-guessed fallback value.
        return 10 ** -max_decimals

    @staticmethod
    def _decimal_places(token: str) -> int:
        return len(token.split(".", 1)[1]) if "." in token else 0

    @staticmethod
    def _tokenize_row(line: str, delimiter: str) -> Optional[List[str]]:
        parts = [part for part in line.replace(",", ".").split(delimiter) if part != ""]
        if len(parts) < 3:
            parts = [part for part in line.replace(",", ".").split() if part != ""]
            if len(parts) < 3:
                return None
        try:
            int(parts[0])
        except ValueError:
            return None
        return parts

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

    @classmethod
    def _parse_row(cls, line: str, delimiter: str) -> Optional[Tuple[int, Point]]:
        parts = cls._tokenize_row(line, delimiter)
        if parts is None:
            return None
        number = int(parts[0])

        file_x = float(parts[1]) if len(parts) > 1 else 0.0
        file_y = float(parts[2]) if len(parts) > 2 else 0.0
        file_h = float(parts[3]) if len(parts) > 3 else 0.0
        return number, Point(x=file_y, y=file_x, h=file_h)
