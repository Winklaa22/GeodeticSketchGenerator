from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, Optional, Tuple

from ezdxf.addons.drawing.config import (
    BackgroundPolicy,
    ColorPolicy,
    Configuration,
    LinePolicy,
    LineweightPolicy,
    TextPolicy,
)
from ezdxf.addons.drawing.layout import (
    Margins,
    Page,
    PageAlignment,
    Settings,
    Units,
    fit_to_page,
)
from ezdxf.math import Matrix44, Vec2

MM_PER_METER = 1000.0
MIN_LINEWEIGHT_UNITS_PER_MM = 300.0 / 25.4
POINT_DIAMETER_MM = 0.5
POINT_RADIUS_MM = POINT_DIAMETER_MM / 2.0
PAPER_COLOR = "#ffffff"
ANNOTATION_TEXT_MM = 2.5

SCALE_MODE_FIXED = "fixed"
SCALE_MODE_FIT = "fit"

COLOR_MODE_COLOR = "color"
COLOR_MODE_MONOCHROME = "monochrome"


@dataclass(frozen=True)
class PageSizeSpec:
    key: str
    name: str
    width_mm: float
    height_mm: float

    @property
    def label(self) -> str:
        return f"{self.name} — {self.width_mm:.0f} × {self.height_mm:.0f} mm"


PAGE_SIZES: Tuple[PageSizeSpec, ...] = (
    PageSizeSpec("a4", "A4", 210.0, 297.0),
    PageSizeSpec("a3", "A3", 297.0, 420.0),
    PageSizeSpec("a2", "A2", 420.0, 594.0),
    PageSizeSpec("a1", "A1", 594.0, 841.0),
    PageSizeSpec("a0", "A0", 841.0, 1189.0),
    PageSizeSpec("letter", "Letter", 215.9, 279.4),
)

PAGE_SIZE_BY_KEY: Dict[str, PageSizeSpec] = {spec.key: spec for spec in PAGE_SIZES}
DEFAULT_PAGE_KEY = "a4"

SCALE_PRESETS: Tuple[int, ...] = (100, 250, 500, 1000, 2000)
DEFAULT_SCALE_DENOMINATOR = 500


@dataclass(frozen=True)
class PlotOptions:
    page_key: str = DEFAULT_PAGE_KEY
    landscape: bool = True
    scale_mode: str = SCALE_MODE_FIXED
    scale_denominator: int = DEFAULT_SCALE_DENOMINATOR
    margin_mm: float = 10.0
    color_mode: str = COLOR_MODE_COLOR
    min_lineweight_mm: float = 0.13


@dataclass(frozen=True)
class StrokeStyle:
    units_per_mm: float
    min_lineweight_mm: float

    def pen_width(self, lineweight_mm: float) -> float:
        return max(lineweight_mm, self.min_lineweight_mm) * self.units_per_mm

    def point_radius(self) -> float:
        return POINT_RADIUS_MM * self.units_per_mm


def page_spec(options: PlotOptions) -> PageSizeSpec:
    return PAGE_SIZE_BY_KEY.get(options.page_key, PAGE_SIZE_BY_KEY[DEFAULT_PAGE_KEY])


def page_size_mm(options: PlotOptions) -> Tuple[float, float]:
    spec = page_spec(options)
    if options.landscape:
        return spec.height_mm, spec.width_mm
    return spec.width_mm, spec.height_mm


def page_for(options: PlotOptions, extra_bottom_margin_mm: float = 0.0) -> Page:
    width, height = page_size_mm(options)
    margin = options.margin_mm
    margins = Margins(margin, margin, margin + extra_bottom_margin_mm, margin)
    return Page(width, height, Units.mm, margins)


def denominator(options: PlotOptions) -> int:
    return max(1, int(options.scale_denominator))


def units_per_mm(options: PlotOptions) -> float:
    return denominator(options) / MM_PER_METER


def sheet_size_in_units(options: PlotOptions) -> Tuple[float, float]:
    factor = units_per_mm(options)
    width, height = page_size_mm(options)
    return width * factor, height * factor


def printable_size_in_units(options: PlotOptions) -> Tuple[float, float]:
    factor = units_per_mm(options)
    width, height = page_size_mm(options)
    inset = 2.0 * options.margin_mm
    return max(width - inset, 0.0) * factor, max(height - inset, 0.0) * factor


def margin_in_units(options: PlotOptions) -> float:
    return options.margin_mm * units_per_mm(options)


def fit_denominator(content_size: Vec2, page: Page) -> int:
    size = Vec2(content_size)
    if size.x <= 0.0 or size.y <= 0.0:
        return DEFAULT_SCALE_DENOMINATOR
    factor = fit_to_page(size, page)
    if factor <= 0.0:
        return DEFAULT_SCALE_DENOMINATOR
    return max(1, math.ceil(MM_PER_METER / factor))


def resolved_options(
    options: PlotOptions, content_size: Optional[Vec2], extra_bottom_margin_mm: float = 0.0
) -> PlotOptions:
    if options.scale_mode != SCALE_MODE_FIT or content_size is None:
        return options
    page = page_for(options, extra_bottom_margin_mm)
    return replace(options, scale_denominator=fit_denominator(content_size, page))


def settings_for(options: PlotOptions) -> Settings:
    page = page_for(options)
    return Settings(
        scale=MM_PER_METER / denominator(options),
        fit_page=False,
        page_alignment=PageAlignment.MIDDLE_CENTER,
        crop_at_margins=True,
        output_coordinate_space=max(page.width_in_mm, page.height_in_mm),
    )


def model_stroke_style(options: PlotOptions) -> StrokeStyle:
    return StrokeStyle(units_per_mm(options), options.min_lineweight_mm)


def paper_stroke_style(options: PlotOptions) -> StrokeStyle:
    return StrokeStyle(1.0, options.min_lineweight_mm)


def render_configuration(options: PlotOptions) -> Configuration:
    color_policy = (
        ColorPolicy.BLACK
        if options.color_mode == COLOR_MODE_MONOCHROME
        else ColorPolicy.COLOR
    )
    return Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=color_policy,
        lineweight_policy=LineweightPolicy.ABSOLUTE,
        min_lineweight=options.min_lineweight_mm * MIN_LINEWEIGHT_UNITS_PER_MM,
        line_policy=LinePolicy.ACCURATE,
        text_policy=TextPolicy.FILLING,
    )


def scale_label(options: PlotOptions) -> str:
    return f"1:{denominator(options)}"


def sheet_label(options: PlotOptions) -> str:
    orientation = "landscape" if options.landscape else "portrait"
    return f"{page_spec(options).name} {orientation} · {scale_label(options)}"


def normalize_degrees(value: float) -> float:
    return ((value + 180.0) % 360.0) - 180.0


def content_rotation_matrix(rotation_degrees: float, pivot: Tuple[float, float]) -> Matrix44:
    cx, cy = pivot
    return Matrix44.chain(
        Matrix44.translate(-cx, -cy, 0),
        Matrix44.z_rotate(math.radians(rotation_degrees)),
        Matrix44.translate(cx, cy, 0),
    )


def rotated_bbox_extents(
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    pivot: Tuple[float, float],
    rotation_degrees: float,
) -> Tuple[float, float, float, float]:
    if not rotation_degrees:
        return xmin, ymin, xmax, ymax
    cx, cy = pivot
    angle = math.radians(rotation_degrees)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    corners = ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax))
    rotated = [
        (cx + (x - cx) * cos_a - (y - cy) * sin_a, cy + (x - cx) * sin_a + (y - cy) * cos_a)
        for x, y in corners
    ]
    xs = [point[0] for point in rotated]
    ys = [point[1] for point in rotated]
    return min(xs), min(ys), max(xs), max(ys)
