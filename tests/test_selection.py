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


def test_parse_ranges_joins_several_ranges_without_duplicates() -> None:
    ranges = [("1", "5"), ("4", "8"), ("9", "11")]
    assert SelectionParser.parse_ranges(ranges) == list(range(1, 12))


def test_parse_ranges_lists_the_points_in_ascending_order_whatever_order_the_ranges_were_entered_in() -> None:
    assert SelectionParser.parse_ranges([("9", "11"), ("1", "3")]) == [1, 2, 3, 9, 10, 11]


def test_parse_ranges_normalizes_a_reversed_range() -> None:
    assert SelectionParser.parse_ranges([("8", "4")]) == [4, 5, 6, 7, 8]


def test_parse_ranges_skips_blank_or_unreadable_ranges() -> None:
    ranges = [("", ""), ("3", ""), ("x", "5"), ("2", "4")]
    assert SelectionParser.parse_ranges(ranges) == [2, 3, 4]


def test_parse_ranges_is_empty_without_any_valid_range() -> None:
    assert SelectionParser.parse_ranges([]) == []
    assert SelectionParser.parse_ranges([("", ""), ("a", "b")]) == []


def test_parse_ranges_accepts_a_single_point_range() -> None:
    assert SelectionParser.parse_ranges([("5", "5")]) == [5]


def test_range_runs_keep_ranges_with_a_gap_apart() -> None:
    assert SelectionParser.parse_range_runs([("13", "17"), ("5", "9")]) == [[5, 6, 7, 8, 9], [13, 14, 15, 16, 17]]


def test_range_runs_merge_overlapping_and_touching_ranges() -> None:
    assert SelectionParser.parse_range_runs([("1", "5"), ("4", "8"), ("9", "11")]) == [list(range(1, 12))]


def test_range_runs_are_empty_without_a_valid_range() -> None:
    assert SelectionParser.parse_range_runs([("", ""), ("a", "2")]) == []
