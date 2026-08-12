"""Tests for core.script_generator.ScriptGenerator and its drawing strategies."""
from __future__ import annotations

import pytest

from core.config import CableOptions, GenerationConfig, HeightsOptions, PointsOptions
from core.draw_modes import DrawMode
from core.exceptions import InvalidLayerNameError, NoDataError, NoSelectionError
from core.script_generator import ScriptGenerator
from models.point import Point


@pytest.fixture
def points() -> dict[int, Point]:
    return {
        1: Point(x=0.0, y=0.0, h=10.0),
        2: Point(x=10.0, y=0.0, h=11.0),
        3: Point(x=10.0, y=10.0, h=12.0),
    }


@pytest.fixture
def generator() -> ScriptGenerator:
    return ScriptGenerator()


def test_generate_raises_when_no_points(generator: ScriptGenerator) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    with pytest.raises(NoDataError):
        generator.generate({}, [], config)


def test_generate_raises_when_no_selection(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    with pytest.raises(NoSelectionError):
        generator.generate(points, [], config)


def test_generate_raises_when_layer_name_blank(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="   ", draw_mode=DrawMode.LINES)
    with pytest.raises(InvalidLayerNameError):
        generator.generate(points, [1, 2, 3], config)


def test_header_contains_layer_name(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="MyLayer", draw_mode=DrawMode.LINES)
    script = generator.generate(points, [1, 2, 3], config)
    assert script.splitlines()[:3] == ["-LAYER", "MAKE MyLayer", ""]


def test_lines_mode_emits_command_and_xyz_coordinates(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.LINES)
    lines = generator.generate(points, [1, 2, 3], config).splitlines()
    assert "LINE" in lines
    assert "0.0,0.0,10.0" in lines
    assert "10.0,0.0,11.0" in lines


def test_pline_mode_emits_command_and_xy_only(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.PLINES)
    lines = generator.generate(points, [1, 2], config).splitlines()
    assert "PLINE" in lines
    assert "0.0,0.0" in lines
    assert "0.0,0.0,10.0" not in lines


def test_poly3d_mode_emits_command_and_xyz_coordinates(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(layer_name="0", draw_mode=DrawMode.POLY3D)
    lines = generator.generate(points, [1, 2], config).splitlines()
    assert "3DPOLY" in lines
    assert "0.0,0.0,10.0" in lines


def test_points_mode_draws_circles_with_diameter_derived_radius(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=False, diameter=0.1),
    )
    lines = generator.generate(points, [1, 2, 3], config).splitlines()
    assert "CIRCLE 0.0,0.0,10.0 0.05" in lines
    assert not any(line.startswith("-TEXT") for line in lines)


def test_points_mode_adds_number_labels_when_enabled(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    lines = generator.generate(points, [1, 2, 3], config).splitlines()
    text_lines = [line for line in lines if line.startswith("-TEXT")]
    assert len(text_lines) == 3
    assert any(line.endswith("0 1") for line in text_lines)
    assert any(line.endswith("0 2") for line in text_lines)
    assert any(line.endswith("0 3") for line in text_lines)


def test_points_mode_cabinet_shrinks_last_six_labels(generator: ScriptGenerator) -> None:
    points = {n: Point(x=float(n), y=0.0, h=1.0) for n in range(1, 8)}
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.POINTS,
        cabinet_mode=True,
        points=PointsOptions(numbers_enabled=True, font_size=0.6, diameter=0.1),
    )
    lines = generator.generate(points, list(range(1, 8)), config).splitlines()
    text_lines = [line for line in lines if line.startswith("-TEXT")]
    # Point 1 is not among the last 6 selected -> normal size 0.6.
    assert any(" 0.6 0 1" in line for line in text_lines)
    # Point 2 is among the last 6 selected -> shrunk to 0.3, no offset.
    assert any(line.replace("-TEXT ", "") == "2.0,0.0,1.0 0.3 0 2" for line in text_lines)


def test_heights_mode_respects_frequency_and_rounds_height_up(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.HEIGHTS,
        heights=HeightsOptions(font_size=0.6, frequency=2),
    )
    lines = generator.generate(points, [1, 2, 3], config).splitlines()
    text_lines = [line for line in lines if line.startswith("-TEXT")]
    assert len(text_lines) == 1  # only point #2 is a multiple of frequency=2
    assert text_lines[0].endswith(" 11.0")  # ceil(11.0 * 10) / 10 == 11.0


def test_cable_marks_use_segment_midpoint_and_custom_text(generator: ScriptGenerator, points) -> None:
    config = GenerationConfig(
        layer_name="0",
        draw_mode=DrawMode.CABLE_MARKS,
        cable=CableOptions(font_size=0.6, frequency=1, marks_text="CBL"),
    )
    lines = generator.generate(points, [1, 2, 3], config).splitlines()
    text_lines = [line for line in lines if line.startswith("-TEXT")]
    # Point 3 has no successor in the selection, so only points 1 and 2 emit marks.
    assert len(text_lines) == 2
    assert all(line.endswith("CBL") for line in text_lines)
