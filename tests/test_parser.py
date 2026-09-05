from __future__ import annotations

import pytest

from core.exceptions import EmptyFileError, NoValidPointsError
from core.parser import DelimiterMode, PointFileParser


@pytest.fixture
def parser() -> PointFileParser:
    return PointFileParser()


def test_header_row_is_skipped_and_xy_is_swapped(parser: PointFileParser) -> None:
    data = parser.parse_lines(["Numer X Y H", "1 100 200 5", "2 110 210 6"], DelimiterMode.SPACE)
    assert data[1].x == 200 and data[1].y == 100
    assert data[2].x == 210


def test_no_header_row(parser: PointFileParser) -> None:
    data = parser.parse_lines(["1 100 200 5", "2 110 210 6"], DelimiterMode.SPACE)
    assert len(data) == 2


def test_comma_decimal_separator(parser: PointFileParser) -> None:
    data = parser.parse_lines(["Numer X Y", "3 100,5 200,25"], DelimiterMode.SPACE)
    assert data[3].x == pytest.approx(200.25)
    assert data[3].y == pytest.approx(100.5)


def test_tab_delimiter(parser: PointFileParser) -> None:
    data = parser.parse_lines(["Numer\tX\tY\tH", "1\t100\t200\t5"], DelimiterMode.TAB)
    assert data[1].x == 200


def test_rows_with_non_numeric_point_number_are_skipped(parser: PointFileParser) -> None:
    data = parser.parse_lines(["Numer X Y", "A 10 20", "4 30 40"], DelimiterMode.SPACE)
    assert 1 not in data
    assert 4 in data


def test_auto_detect_prefers_tab_over_space() -> None:
    assert PointFileParser.detect_delimiter("1\t2\t3") == "\t"
    assert PointFileParser.detect_delimiter("1 2 3") == " "


def test_auto_delimiter_mode_uses_detection(parser: PointFileParser) -> None:
    data = parser.parse_lines(["Numer\tX\tY\tH", "1\t100\t200\t5"], DelimiterMode.AUTO)
    assert data[1].x == 200


def test_empty_input_raises_empty_file_error(parser: PointFileParser) -> None:
    with pytest.raises(EmptyFileError):
        parser.parse_lines([], DelimiterMode.AUTO)


def test_all_rows_invalid_raises_no_valid_points_error(parser: PointFileParser) -> None:
    with pytest.raises(NoValidPointsError):
        parser.parse_lines(["Numer X Y", "bad row"], DelimiterMode.SPACE)


def test_missing_height_defaults_to_zero(parser: PointFileParser) -> None:
    data = parser.parse_lines(["1 100 200"], DelimiterMode.SPACE)
    assert data[1].h == 0.0


def test_row_with_too_few_fields_falls_back_to_whitespace_split(parser: PointFileParser) -> None:
    data = parser.parse_lines(["1 100 200 5"], DelimiterMode.TAB)
    assert data[1].x == 200 and data[1].y == 100 and data[1].h == 5


def test_estimate_quantum_picks_the_finest_decimal_places_seen_across_x_and_y(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["Numer X Y H", "1 100.5 200.25 5", "2 110.1 210.1 6"], DelimiterMode.SPACE)
    assert q == pytest.approx(0.01)


def test_estimate_quantum_ignores_the_height_column(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["Numer X Y H", "1 100.5 200.5 5.12345"], DelimiterMode.SPACE)
    assert q == pytest.approx(0.1)


def test_estimate_quantum_handles_comma_decimal_separator(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["Numer X Y", "3 100,5 200,25"], DelimiterMode.SPACE)
    assert q == pytest.approx(0.01)


def test_estimate_quantum_falls_back_to_one_for_all_integer_coordinates(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["1 100 200 5", "2 110 210 6"], DelimiterMode.SPACE)
    assert q == pytest.approx(1.0)


def test_estimate_quantum_skips_the_header_row_like_parse_lines_does(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["Numer X Y H", "1 100.123 200 5"], DelimiterMode.SPACE)
    assert q == pytest.approx(0.001)


def test_estimate_quantum_respects_an_explicit_delimiter_mode(parser: PointFileParser) -> None:
    q = parser.estimate_quantum(["Numer\tX\tY\tH", "1\t100.25\t200\t5"], DelimiterMode.TAB)
    assert q == pytest.approx(0.01)


def test_estimate_quantum_raises_empty_file_error_on_no_lines(parser: PointFileParser) -> None:
    with pytest.raises(EmptyFileError):
        parser.estimate_quantum([], DelimiterMode.AUTO)


def test_estimate_quantum_raises_no_valid_points_error_when_no_row_parses(parser: PointFileParser) -> None:
    with pytest.raises(NoValidPointsError):
        parser.estimate_quantum(["Numer X Y", "bad row"], DelimiterMode.SPACE)
