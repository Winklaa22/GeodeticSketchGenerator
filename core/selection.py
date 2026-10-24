from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from models.point import Point


class SelectionParser:

    @staticmethod
    def parse_separate(text: str) -> List[int]:
        return [int(token.strip()) for token in text.split(",") if token.strip().isdigit()]

    @staticmethod
    def _expand(start: int, end: int) -> List[int]:
        return list(range(min(start, end), max(start, end) + 1))

    @staticmethod
    def parse_range(text: str) -> List[int]:
        try:
            start_text, end_text = (part.strip() for part in text.split("-"))
            start, end = int(start_text), int(end_text)
        except ValueError:
            return []
        return SelectionParser._expand(start, end)

    @staticmethod
    def _parse_bounds(start_text: str, end_text: str) -> Optional[Tuple[int, int]]:
        start_text, end_text = start_text.strip(), end_text.strip()
        if not (start_text.isdigit() and end_text.isdigit()):
            return None
        return int(start_text), int(end_text)

    @staticmethod
    def parse_range_runs(ranges: Sequence[Tuple[str, str]]) -> List[List[int]]:
        spans: List[Tuple[int, int]] = []
        for start_text, end_text in ranges:
            bounds = SelectionParser._parse_bounds(start_text, end_text)
            if bounds is not None:
                spans.append((min(bounds), max(bounds)))
        merged: List[List[int]] = []
        for low, high in sorted(spans):
            if merged and low <= merged[-1][1] + 1:
                merged[-1][1] = max(merged[-1][1], high)
            else:
                merged.append([low, high])
        return [list(range(low, high + 1)) for low, high in merged]

    @staticmethod
    def parse_ranges(ranges: Sequence[Tuple[str, str]]) -> List[int]:
        return [number for run in SelectionParser.parse_range_runs(ranges) for number in run]

    @staticmethod
    def all_points(data: Dict[int, Point]) -> List[int]:
        return sorted(data.keys())
