from __future__ import annotations

from core.selection import SelectionParser
from models.point import Point


def test_parse_separate_ignores_whitespace_and_non_numeric_tokens() -> None:
    assert SelectionParser.parse_separate(" 1, 2,x, 3 ") == [1, 2, 3]


def test_parse_range_returns_inclusive_ascending_list() -> None:
    assert SelectionParser.parse_range("1-7") == [1, 2, 3, 4, 5, 6, 7]


def test_parse_range_normalizes_descending_input() -> None:
    assert SelectionParser.parse_range("7-1") == [1, 2, 3, 4, 5, 6, 7]


def test_parse_range_returns_empty_list_on_malformed_input() -> None:
    assert SelectionParser.parse_range("not-a-range") == []
    assert SelectionParser.parse_range("1-2-3") == []


def test_all_points_returns_sorted_keys() -> None:
    data = {3: Point(0, 0, 0), 1: Point(0, 0, 0), 2: Point(0, 0, 0)}
    assert SelectionParser.all_points(data) == [1, 2, 3]
