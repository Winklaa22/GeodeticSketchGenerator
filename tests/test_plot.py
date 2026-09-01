from __future__ import annotations

from ezdxf.math import Vec2

from core.plot import (
    ANNOTATION_TEXT_MM,
    COLOR_MODE_MONOCHROME,
    PAGE_SIZES,
    POINT_RADIUS_MM,
    SCALE_MODE_FIT,
    content_rotation_matrix,
    normalize_degrees,
    rotated_bbox_extents,
    zoomed_denominator,
    PlotOptions,
    StrokeStyle,
    margin_in_units,
    model_stroke_style,
    paper_stroke_style,
    printable_size_in_units,
    render_configuration,
    resolved_options,
    scale_label,
    sheet_label,
    sheet_size_in_units,
    units_per_mm,
)


def test_units_per_mm_converts_paper_millimetres_to_metres() -> None:
    assert units_per_mm(PlotOptions(scale_denominator=500)) == 0.5
    assert units_per_mm(PlotOptions(scale_denominator=1000)) == 1.0


def test_units_per_mm_guards_against_zero_denominator() -> None:
    assert units_per_mm(PlotOptions(scale_denominator=0)) == 0.001


def test_sheet_size_in_units_swaps_axes_for_landscape() -> None:
    portrait = PlotOptions(page_key="a3", landscape=False, scale_denominator=500)
    landscape = PlotOptions(page_key="a3", landscape=True, scale_denominator=500)
    assert sheet_size_in_units(portrait) == (148.5, 210.0)
    assert sheet_size_in_units(landscape) == (210.0, 148.5)


def test_printable_size_in_units_insets_both_margins() -> None:
    options = PlotOptions(page_key="a3", landscape=True, scale_denominator=500, margin_mm=10.0)
    assert printable_size_in_units(options) == (200.0, 138.5)
    assert margin_in_units(options) == 5.0


def test_stroke_style_clamps_to_minimum_lineweight() -> None:
    style = StrokeStyle(units_per_mm=1.0, min_lineweight_mm=0.13)
    assert style.pen_width(0.09) == 0.13
    assert style.pen_width(0.50) == 0.50


def test_model_and_paper_stroke_styles_describe_the_same_stroke() -> None:
    options = PlotOptions(scale_denominator=500, min_lineweight_mm=0.13)
    model = model_stroke_style(options)
    paper = paper_stroke_style(options)
    factor = units_per_mm(options)
    for lineweight in (0.0, 0.05, 0.13, 0.25, 0.7, 2.0):
        assert model.pen_width(lineweight) == paper.pen_width(lineweight) * factor
    assert model.point_radius() == paper.point_radius() * factor


def test_paper_stroke_style_measures_in_millimetres() -> None:
    paper = paper_stroke_style(PlotOptions(min_lineweight_mm=0.13))
    assert paper.pen_width(0.05) == 0.13
    assert paper.point_radius() == POINT_RADIUS_MM


def test_model_stroke_style_scales_with_the_plot_scale() -> None:
    thin = model_stroke_style(PlotOptions(scale_denominator=100, min_lineweight_mm=0.13))
    wide = model_stroke_style(PlotOptions(scale_denominator=1000, min_lineweight_mm=0.13))
    assert wide.pen_width(0.13) == thin.pen_width(0.13) * 10.0


def test_resolved_options_is_a_no_op_for_fixed_scale() -> None:
    options = PlotOptions(scale_denominator=250)
    assert resolved_options(options, Vec2(100.0, 50.0)) is options


def test_resolved_options_keeps_scale_when_content_size_is_unknown() -> None:
    options = PlotOptions(scale_mode=SCALE_MODE_FIT, scale_denominator=250)
    assert resolved_options(options, None) is options


def test_resolved_options_fits_content_inside_the_printable_area() -> None:
    options = PlotOptions(page_key="a4", landscape=True, scale_mode=SCALE_MODE_FIT)
    resolved = resolved_options(options, Vec2(100.0, 50.0))
    width, height = printable_size_in_units(resolved)
    assert width >= 100.0
    assert height >= 50.0
    assert min(width - 100.0, height - 50.0) < 1.0


def test_scale_label_reads_as_a_ratio() -> None:
    assert scale_label(PlotOptions(scale_denominator=250)) == "1:250"


def test_render_configuration_forces_black_ink_for_monochrome() -> None:
    color = render_configuration(PlotOptions())
    mono = render_configuration(PlotOptions(color_mode=COLOR_MODE_MONOCHROME))
    assert color.color_policy != mono.color_policy
    assert color.background_policy == mono.background_policy


def test_page_size_labels_name_the_format_and_its_millimetres() -> None:
    labels = {spec.key: spec.label for spec in PAGE_SIZES}
    assert labels["a4"] == "A4 — 210 × 297 mm"
    assert labels["a0"] == "A0 — 841 × 1189 mm"
    assert labels["letter"] == "Letter — 216 × 279 mm"


def test_sheet_label_reads_as_the_caption_under_the_page() -> None:
    assert sheet_label(PlotOptions(page_key="a3", landscape=True, scale_denominator=500)) == (
        "A3 landscape · 1:500"
    )
    assert sheet_label(PlotOptions(page_key="letter", landscape=False, scale_denominator=1000)) == (
        "Letter portrait · 1:1000"
    )


def test_annotation_height_prints_the_same_size_at_any_scale() -> None:
    for denominator in (100, 500, 2000):
        options = PlotOptions(scale_denominator=denominator)
        height_in_units = ANNOTATION_TEXT_MM * units_per_mm(options)
        assert height_in_units / units_per_mm(options) == ANNOTATION_TEXT_MM


def test_zoomed_denominator_shrinks_when_zooming_in() -> None:
    assert zoomed_denominator(500, 1.2) == 417


def test_zoomed_denominator_grows_when_zooming_out() -> None:
    assert zoomed_denominator(500, 1 / 1.2) == 600


def test_zoomed_denominator_never_drops_below_one() -> None:
    assert zoomed_denominator(1, 100.0) == 1


def test_zoomed_denominator_ignores_a_non_positive_factor() -> None:
    assert zoomed_denominator(500, 0.0) == 500
    assert zoomed_denominator(500, -2.0) == 500


def test_normalize_degrees_is_a_no_op_inside_the_range() -> None:
    assert normalize_degrees(0.0) == 0.0
    assert normalize_degrees(45.0) == 45.0
    assert normalize_degrees(-179.0) == -179.0


def test_normalize_degrees_wraps_values_outside_plus_minus_180() -> None:
    assert normalize_degrees(180.0) == -180.0
    assert normalize_degrees(190.0) == -170.0
    assert normalize_degrees(-190.0) == 170.0
    assert normalize_degrees(360.0) == 0.0
    assert normalize_degrees(720.0 + 30.0) == 30.0


def test_content_rotation_matrix_leaves_the_pivot_fixed() -> None:
    matrix = content_rotation_matrix(37.0, (12.0, -8.0))
    result = matrix.transform((12.0, -8.0, 0.0))
    assert abs(result.x - 12.0) < 1e-9
    assert abs(result.y - (-8.0)) < 1e-9


def test_content_rotation_matrix_turns_counterclockwise_for_positive_angles() -> None:
    matrix = content_rotation_matrix(90.0, (0.0, 0.0))
    result = matrix.transform((1.0, 0.0, 0.0))
    assert abs(result.x - 0.0) < 1e-9
    assert abs(result.y - 1.0) < 1e-9


def test_content_rotation_matrix_is_a_no_op_at_zero_degrees() -> None:
    matrix = content_rotation_matrix(0.0, (5.0, 5.0))
    result = matrix.transform((3.0, 9.0, 0.0))
    assert abs(result.x - 3.0) < 1e-9
    assert abs(result.y - 9.0) < 1e-9


def test_rotated_bbox_extents_is_unchanged_at_zero_rotation() -> None:
    assert rotated_bbox_extents(0.0, 0.0, 10.0, 4.0, (5.0, 2.0), 0.0) == (0.0, 0.0, 10.0, 4.0)


def test_rotated_bbox_extents_matches_the_standard_rotated_rect_formula() -> None:
    xmin, ymin, xmax, ymax = rotated_bbox_extents(-5.0, -2.0, 5.0, 2.0, (0.0, 0.0), 45.0)
    width, height = xmax - xmin, ymax - ymin
    expected = 10.0 * 0.7071067811865476 + 4.0 * 0.7071067811865476
    assert abs(width - expected) < 1e-9
    assert abs(height - expected) < 1e-9
    assert abs((xmin + xmax) / 2.0) < 1e-9
    assert abs((ymin + ymax) / 2.0) < 1e-9


def test_rotated_bbox_extents_keeps_a_square_the_same_size_at_90_degrees() -> None:
    xmin, ymin, xmax, ymax = rotated_bbox_extents(0.0, 0.0, 4.0, 4.0, (0.0, 0.0), 90.0)
    assert abs((xmax - xmin) - 4.0) < 1e-9
    assert abs((ymax - ymin) - 4.0) < 1e-9


def test_rotated_bbox_extents_shifts_with_a_pivot_away_from_the_box() -> None:
    xmin, ymin, xmax, ymax = rotated_bbox_extents(0.0, 0.0, 2.0, 2.0, (10.0, 0.0), 90.0)
    assert xmin > 5.0 and xmax > 5.0
