from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Sequence, Tuple

from PyQt6 import QtCore as qc, QtGui as qg

from ezdxf.addons.drawing import Frontend, RenderContext, layout, recorder
from ezdxf.addons.drawing.backend import Backend, BkPath2d, BkPoints2d, ImageData
from ezdxf.addons.drawing.config import Configuration
from ezdxf.addons.drawing.layout import Margins, Page, Settings
from ezdxf.addons.drawing.properties import BackendProperties
from ezdxf.addons.drawing.type_hints import Color
from ezdxf.math import BoundingBox2d, Vec2

from core.dxf_document import DXFDocument
from core.plot import (
    PlotOptions,
    StrokeStyle,
    content_rotation_matrix,
    page_for,
    paper_stroke_style,
    render_configuration,
    settings_for,
)
from core.table_template import (
    BORDER_WIDTH_MM,
    CELL_PADDING_MM,
    Rect,
    ResolvedCell,
    TableTemplate,
    capped_table_width,
    default_template,
    table_layout,
)
from ui.dxf.backend import qcolor_from, qcolor_on_paper, to_qpainter_path
from ui.dxf.detail_render import detail_players
from ui.dxf.page_frame import PageFrame
from ui.dxf.stamp_cache import stamp_cache
from ui.i18n import tr
from ui.loading_overlay import ProgressFn

RECORD_BAND = 40
RESOLUTION_DPI = 1200
MM_PER_INCH = 25.4
CROP_PRECISION_MM = 0.1
TEXT_RASTER_SCALE = 32.0

_ALIGN_H = {
    "left": qc.Qt.AlignmentFlag.AlignLeft,
    "center": qc.Qt.AlignmentFlag.AlignHCenter,
    "right": qc.Qt.AlignmentFlag.AlignRight,
}
_ALIGN_V = {
    "top": qc.Qt.AlignmentFlag.AlignTop,
    "middle": qc.Qt.AlignmentFlag.AlignVCenter,
    "bottom": qc.Qt.AlignmentFlag.AlignBottom,
}


class QtPainterBackend(Backend):

    def __init__(self, painter: qg.QPainter, page: Page, stroke: StrokeStyle) -> None:
        super().__init__()
        self._painter = painter
        self._page = page
        self._stroke = stroke
        self._no_pen = qg.QPen(qc.Qt.PenStyle.NoPen)
        self._no_brush = qg.QBrush(qc.Qt.BrushStyle.NoBrush)

    def _pen(self, properties: BackendProperties) -> qg.QPen:
        pen = qg.QPen(qcolor_on_paper(properties.color), self._stroke.pen_width(properties.lineweight))
        pen.setCapStyle(qc.Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(qc.Qt.PenJoinStyle.RoundJoin)
        return pen

    @staticmethod
    def _brush(color: Color) -> qg.QBrush:
        return qg.QBrush(qcolor_on_paper(color), qc.Qt.BrushStyle.SolidPattern)

    def set_background(self, color: Color) -> None:
        rect = qc.QRectF(0.0, 0.0, self._page.width_in_mm, self._page.height_in_mm)
        self._painter.fillRect(rect, qcolor_from(color))

    def draw_point(self, pos: Vec2, properties: BackendProperties) -> None:
        radius = self._stroke.point_radius()
        self._painter.setPen(self._no_pen)
        self._painter.setBrush(self._brush(properties.color))
        self._painter.drawEllipse(qc.QPointF(pos.x, pos.y), radius, radius)

    def draw_line(self, start: Vec2, end: Vec2, properties: BackendProperties) -> None:
        if start.isclose(end):
            self.draw_point(start, properties)
            return
        self._painter.setPen(self._pen(properties))
        self._painter.setBrush(self._no_brush)
        self._painter.drawLine(qc.QPointF(start.x, start.y), qc.QPointF(end.x, end.y))

    def draw_solid_lines(
        self, lines: Iterable[Tuple[Vec2, Vec2]], properties: BackendProperties
    ) -> None:
        pen = self._pen(properties)
        self._painter.setPen(pen)
        self._painter.setBrush(self._no_brush)
        for start, end in lines:
            if start.isclose(end):
                self.draw_point(start, properties)
                self._painter.setPen(pen)
                continue
            self._painter.drawLine(qc.QPointF(start.x, start.y), qc.QPointF(end.x, end.y))

    def draw_path(self, path: BkPath2d, properties: BackendProperties) -> None:
        if len(path) == 0:
            return
        self._painter.setPen(self._pen(properties))
        self._painter.setBrush(self._no_brush)
        self._painter.drawPath(to_qpainter_path([path]))

    def draw_filled_paths(
        self, paths: Iterable[BkPath2d], properties: BackendProperties
    ) -> None:
        paths = list(paths)
        if not paths:
            return
        qpath = to_qpainter_path(paths)
        qpath.setFillRule(qc.Qt.FillRule.OddEvenFill)
        self._painter.setPen(self._no_pen)
        self._painter.setBrush(self._brush(properties.color))
        self._painter.drawPath(qpath)

    def draw_filled_polygon(
        self, points: BkPoints2d, properties: BackendProperties
    ) -> None:
        polygon = qg.QPolygonF([qc.QPointF(p.x, p.y) for p in points.vertices()])
        if polygon.isEmpty():
            return
        self._painter.setPen(self._no_pen)
        self._painter.setBrush(self._brush(properties.color))
        self._painter.drawPolygon(polygon)

    def draw_image(self, image_data: ImageData, properties: BackendProperties) -> None:
        return

    def clear(self) -> None:
        return

    def finalize(self) -> None:
        return


def _record(document: DXFDocument, config: Configuration) -> recorder.Recorder:
    rec = recorder.Recorder()
    context = RenderContext(document.drawing)
    Frontend(context, rec, config=config).draw_layout(document.modelspace, finalize=True)
    # Player.replay() pushes its own background onto the target. The detail players never
    # drew a layout, so theirs is the recorder default (black) and would repaint the whole
    # sheet; the sheet's white background has to survive the replay.
    page_background = rec.background
    for _handle, _spec, player in detail_players(document, config):
        player.replay(rec)
    rec.set_background(page_background)
    return rec


def _apply_page(writer: qg.QPdfWriter, page: Page) -> None:
    page_layout = writer.pageLayout()
    page_layout.setMode(qg.QPageLayout.Mode.FullPageMode)
    page_layout.setPageSize(
        qg.QPageSize(
            qc.QSizeF(page.width_in_mm, page.height_in_mm), qg.QPageSize.Unit.Millimeter
        )
    )
    page_layout.setMargins(qc.QMarginsF(0.0, 0.0, 0.0, 0.0))
    writer.setPageLayout(page_layout)


def _make_writer(path: str, page: Page, title: str) -> qg.QPdfWriter:
    writer = qg.QPdfWriter(path)
    _apply_page(writer, page)
    writer.setResolution(RESOLUTION_DPI)
    if title:
        writer.setTitle(title)
    return writer


def _replay(
    player: recorder.Player,
    painter: qg.QPainter,
    page: Page,
    settings: Settings,
    render_box: BoundingBox2d,
    stroke: StrokeStyle,
) -> None:
    output = layout.Layout(render_box, flip_y=True)
    # render_box is the whole sheet, so it has to land on the whole page. Placing it
    # against the real page would instead centre it inside the *margin* box, and since
    # the bottom margin carries the title block that pushes the drawing up by half the
    # table height. The preview draws the sheet edge to edge, so that offset is exactly
    # how the export drifts away from it. A zero-margin copy of the page maps the sheet
    # 1:1; the real page still drives the crop and the backend below.
    full_page = Page(page.width, page.height, page.units, Margins.all(0.0))
    matrix = output.get_placement_matrix(full_page, settings=settings, top_origin=True)
    player.transform(matrix)
    if settings.crop_at_margins:
        p1, p2 = page.get_margin_rect(top_origin=True)
        output_scale = settings.page_output_scale_factor(page)
        player.crop_rect(
            p1 * output_scale, p2 * output_scale, CROP_PRECISION_MM * output_scale
        )
    player.replay(QtPainterBackend(painter, page, stroke))


@dataclass(frozen=True)
class PlotJob:
    name: str
    options: PlotOptions
    frame: PageFrame
    template: TableTemplate = field(default_factory=default_template)
    sheet_field_values: Dict[str, str] = field(default_factory=dict)


def job_render_box(job: PlotJob) -> BoundingBox2d:
    rect = job.frame.sheet_rect()
    return BoundingBox2d(
        [Vec2(rect.left(), rect.top()), Vec2(rect.right(), rect.bottom())]
    )


def _final_page(job: PlotJob, settings: Settings, render_box: BoundingBox2d) -> Page:
    page = page_for(job.options, job.template.total_height_mm())
    return layout.Layout(render_box, flip_y=True).get_final_page(page, settings)


def _cell_flags(cell: ResolvedCell) -> qc.Qt.AlignmentFlag:
    return _ALIGN_H.get(cell.align, qc.Qt.AlignmentFlag.AlignLeft) | _ALIGN_V.get(
        cell.valign, qc.Qt.AlignmentFlag.AlignTop
    )


def _cell_font(cell: ResolvedCell, scale: float = 1.0) -> qg.QFont:
    font = qg.QFont()
    font.setPixelSize(max(1, round(cell.font_size * scale)))
    font.setBold(cell.bold)
    font.setItalic(cell.italic)
    return font


def _draw_cell_image(painter: qg.QPainter, rect: qc.QRectF, path: str) -> None:
    pixmap = stamp_cache.get(path)
    if pixmap is None or pixmap.isNull() or rect.width() <= 0 or rect.height() <= 0:
        return
    src_w, src_h = pixmap.width(), pixmap.height()
    if src_w <= 0 or src_h <= 0:
        return
    scale = min(rect.width() / src_w, rect.height() / src_h)
    target = qc.QRectF(0.0, 0.0, src_w * scale, src_h * scale)
    target.moveCenter(rect.center())
    painter.setRenderHint(qg.QPainter.RenderHint.SmoothPixmapTransform, True)
    painter.drawPixmap(target, pixmap, qc.QRectF(0.0, 0.0, float(src_w), float(src_h)))


def _draw_cell(painter: qg.QPainter, cell: ResolvedCell) -> None:
    rect = qc.QRectF(cell.rect.x, cell.rect.y, cell.rect.w, cell.rect.h)
    padded = rect.adjusted(CELL_PADDING_MM, CELL_PADDING_MM, -CELL_PADDING_MM, -CELL_PADDING_MM)
    if cell.kind == "image" and cell.image_path:
        _draw_cell_image(painter, padded, cell.image_path)
        return
    if not cell.text:
        return
    # The painter is in mm-space (1 unit = 1mm), so a 2mm header font asks Qt for
    # a ~2px nominal font size, which then gets stretched ~47x by the painter's
    # mm-to-device-pixel transform for the 1200 DPI page. Qt hints/embolds glyphs
    # at that tiny nominal size before the stretch, which is what turns "bold"
    # into the heavy, doubled-looking strokes seen in the exported PDF. Scaling
    # the font up (and the painter down by the same factor) around this call
    # makes Qt rasterize at a realistic pixel size while leaving the actual
    # printed size on the page unchanged.
    painter.save()
    painter.scale(1.0 / TEXT_RASTER_SCALE, 1.0 / TEXT_RASTER_SCALE)
    painter.setFont(_cell_font(cell, TEXT_RASTER_SCALE))
    painter.setPen(qg.QColor(0, 0, 0))
    scaled_rect = qc.QRectF(
        padded.x() * TEXT_RASTER_SCALE,
        padded.y() * TEXT_RASTER_SCALE,
        padded.width() * TEXT_RASTER_SCALE,
        padded.height() * TEXT_RASTER_SCALE,
    )
    painter.drawText(scaled_rect, int(_cell_flags(cell)) | qc.Qt.TextFlag.TextWordWrap, cell.text)
    painter.restore()


def _draw_title_block_chrome(painter: qg.QPainter, page: Page, job: PlotJob) -> None:
    p1, p2 = page.get_margin_rect(top_origin=True)
    map_w, map_h = p2.x - p1.x, p2.y - p1.y
    if map_w <= 0.0:
        return
    table_top = p2.y
    table_bottom = page.height_in_mm - job.options.margin_mm
    table_h = max(table_bottom - table_top, 0.0)

    border_pen = qg.QPen(qg.QColor(0, 0, 0), BORDER_WIDTH_MM)
    painter.setPen(border_pen)
    painter.setBrush(qc.Qt.BrushStyle.NoBrush)
    if map_h > 0.0:
        painter.drawRect(qc.QRectF(p1.x, p1.y, map_w, map_h))
    if table_h <= 0.0:
        return
    table_w = capped_table_width(map_w)
    table_rect = qc.QRectF(p1.x, table_top, table_w, table_h)
    painter.drawRect(table_rect)

    cells = table_layout(
        job.template, Rect(p1.x, table_top, table_w, table_h),
        job.sheet_field_values, job.template.project_field_values, scale=1.0,
    )
    thin_pen = qg.QPen(qg.QColor(0, 0, 0), BORDER_WIDTH_MM * 0.6)
    for cell in cells:
        painter.setPen(thin_pen)
        painter.setBrush(qc.Qt.BrushStyle.NoBrush)
        painter.drawRect(qc.QRectF(cell.rect.x, cell.rect.y, cell.rect.w, cell.rect.h))
        _draw_cell(painter, cell)


def export_sheets(
    document: DXFDocument,
    path: str,
    jobs: Sequence[PlotJob],
    title: str = "",
    progress: Optional[ProgressFn] = None,
) -> Tuple[bool, str]:
    if not jobs:
        return False, tr("pdf_export.no_sheets")

    def report(percent: int) -> None:
        if progress is not None:
            progress(percent)

    try:
        recorders: Dict[Configuration, recorder.Recorder] = {}
        configs = []
        for job in jobs:
            config = render_configuration(job.options)
            if config not in configs:
                configs.append(config)
        for index, config in enumerate(configs):
            recorders[config] = _record(document, config)
            report(RECORD_BAND * (index + 1) // len(configs))
    except Exception as exc:
        return False, tr("pdf_export.could_not_render", error=exc)

    if not any(rec.player().bbox().has_data for rec in recorders.values()):
        return False, tr("pdf_export.empty_drawing")

    painter = None
    writer = None
    try:
        for job_index, job in enumerate(jobs):
            settings = settings_for(job.options)
            render_box = job_render_box(job)
            page = _final_page(job, settings, render_box)
            if page.width_in_mm <= 0.0 or page.height_in_mm <= 0.0:
                return False, tr("pdf_export.invalid_page_size", name=job.name or tr("pdf_export.the_sheet_fallback"))

            if writer is None:
                writer = _make_writer(path, page, title)
                painter = qg.QPainter(writer)
                if not painter.isActive():
                    return False, tr("pdf_export.could_not_write_path", path=path)
                painter.setRenderHint(qg.QPainter.RenderHint.Antialiasing)
            else:
                _apply_page(writer, page)
                writer.newPage()

            player = recorders[render_configuration(job.options)].player().copy()
            if job.frame.rotation:
                pivot = (job.frame.center_x, job.frame.center_y)
                player.transform(content_rotation_matrix(job.frame.rotation, pivot))

            painter.save()
            painter.scale(writer.resolution() / MM_PER_INCH, writer.resolution() / MM_PER_INCH)
            _replay(player, painter, page, settings, render_box, paper_stroke_style(job.options))
            _draw_title_block_chrome(painter, page, job)
            painter.restore()
            report(RECORD_BAND + (100 - RECORD_BAND) * (job_index + 1) // len(jobs))
    except Exception as exc:
        return False, tr("pdf_export.could_not_write_pdf", error=exc)
    finally:
        if painter is not None and painter.isActive():
            painter.end()
    return True, ""
