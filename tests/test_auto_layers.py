from __future__ import annotations

import pytest

from core.auto_layers import AUTO_LAYER_GROUP_BY_MODE_KEY, AUTO_LAYER_RGB, AutoLayerGroup, auto_layer_group


@pytest.mark.parametrize("key", ["route", "heights", "cable"])
def test_everything_about_the_cable_shares_one_layer(key: str) -> None:
    assert auto_layer_group(key) is AutoLayerGroup.CABLE


@pytest.mark.parametrize(
    ("key", "group"),
    [
        ("points", AutoLayerGroup.POINTS),
        ("measurements", AutoLayerGroup.MEASUREMENTS),
        ("pipe", AutoLayerGroup.PIPE),
    ],
)
def test_points_measurements_and_pipe_each_get_their_own_layer(key: str, group: AutoLayerGroup) -> None:
    assert auto_layer_group(key) is group


def test_unknown_mode_has_no_auto_layer() -> None:
    assert auto_layer_group("nonsense") is None


def test_default_colors() -> None:
    assert AUTO_LAYER_RGB[AutoLayerGroup.MEASUREMENTS] == (255, 255, 255)
    assert AUTO_LAYER_RGB[AutoLayerGroup.PIPE] == (255, 255, 255)
    red, green, blue = AUTO_LAYER_RGB[AutoLayerGroup.POINTS]
    assert blue > red and blue > green and blue < 200
    assert AUTO_LAYER_RGB[AutoLayerGroup.CABLE][0] > 200


def test_every_group_has_a_color() -> None:
    assert set(AUTO_LAYER_GROUP_BY_MODE_KEY.values()) <= set(AUTO_LAYER_RGB)
