from __future__ import annotations

from typing import Dict, List

from models.point import Point


class SelectionParser:

    @staticmethod
    def parse_separate(text: str) -> List[int]:
        return [int(token.strip()) for token in text.split(",") if token.strip().isdigit()]

    @staticmethod
    def parse_range(text: str) -> List[int]:
        try:
            start_text, end_text = (part.strip() for part in text.split("-"))
            start, end = int(start_text), int(end_text)
        except ValueError:
            return []
        return list(range(min(start, end), max(start, end) + 1))

    @staticmethod
    def all_points(data: Dict[int, Point]) -> List[int]:
        """Returns every known point number, ascending."""
        return sorted(data.keys())
