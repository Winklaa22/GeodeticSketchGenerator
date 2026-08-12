"""Tests for core.validation helpers."""
from __future__ import annotations

import pytest

from core.exceptions import InvalidLayerNameError, NoDataError, NoSelectionError
from core.validation import ensure_has_data, ensure_selection, resolve_layer_name
from models.point import Point


def test_ensure_has_data_raises_when_no_points_and_no_file() -> None:
    with pytest.raises(NoDataError):
        ensure_has_data({}, "")


def test_ensure_has_data_passes_when_file_selected_even_without_points_yet() -> None:
    ensure_has_data({}, "some/file.txt")  # should not raise


def test_ensure_has_data_passes_when_points_present() -> None:
    ensure_has_data({1: Point(0, 0, 0)}, "")  # should not raise


def test_resolve_layer_name_defaults_blank_input_to_zero() -> None:
    assert resolve_layer_name("") == "0"


def test_resolve_layer_name_strips_whitespace() -> None:
    assert resolve_layer_name("  MyLayer  ") == "MyLayer"


def test_resolve_layer_name_raises_for_whitespace_only_input() -> None:
    with pytest.raises(InvalidLayerNameError):
        resolve_layer_name("   ")


def test_ensure_selection_raises_when_empty() -> None:
    with pytest.raises(NoSelectionError):
        ensure_selection([])
