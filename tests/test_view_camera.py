from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.commands.detail_view import AddDetailViewCommand
from core.commands.draw import AddLineCommand, AddPointCommand
from core.detail_view import DetailViewSpec
from core.plot import (
    PlotOptions,
    content_rotation_matrix,
    paper_stroke_style,
    render_configuration,
    settings_for,
)
from core.project import ProjectState
from core.sheets import SheetSet
from core.table_template import default_template
from ui.dxf.graphics_view import CadGraphicsView
from ui.dxf.items import DETAIL_CONTENT_ROLE, HANDLE_ROLE, PointItem
from ui.dxf.page_frame import page_frame_for
from ui.dxf import pdf_export
from ui.dxf.viewer import DxfViewer
from ui.editor.layout_controller import LayoutController
from ui.editor.layout_panel import LayoutPanel
from ui.editor import window as editor_window


@pytest.fixture(scope="module")
def app():
    return qw.QApplication.instance() or qw.QApplication(["camera-tests", "-platform", "offscreen"])


@pytest.fixture
def view(app):
    widget = CadGraphicsView()
    widget.resize(900, 600)
    widget.show()
    app.processEvents()
    widget.set_page_frame(page_frame_for(PlotOptions(), (6_500_000.0, 5_500_000.0)))
    widget.fit_to_page()
    yield widget
    widget.close()
    widget.deleteLater()
    app.processEvents()


def point_xy(point):
    return point.x(), point.y()


def test_resizing_a_panned_sheet_preserves_the_camera(view, app):
    view.zoom_by(2.0, qc.QPointF(100.0, 100.0))
    view.recenter_on(6_500_060.0, 5_500_060.0)
    center = view.save_view()[1]
    zoom = view.current_zoom_factor()

    for width, height in [(1000, 650), (700, 800), (900, 600)]:
        view.resize(width, height)
        app.processEvents()

    assert point_xy(view.save_view()[1]) == pytest.approx(point_xy(center), abs=1e-7, rel=0)
    assert view.current_zoom_factor() == pytest.approx(zoom)


def test_restoring_a_view_restores_its_zoom_baseline(view):
    view.zoom_by(2.0, qc.QPointF(100.0, 100.0))
    saved = view.save_view()
    view.set_page_frame(None)
    view.scene().addRect(6_500_000.0, 5_500_000.0, 10.0, 10.0)
    view.fit_to_scene()

    view.restore_view(saved)

    assert view.current_zoom_factor() == pytest.approx(2.0)
    assert point_xy(view.save_view()[1]) == pytest.approx(point_xy(saved[1]), abs=1e-7, rel=0)


def test_large_survey_coordinates_keep_the_anchor_at_high_zoom(view):
    view.set_page_frame(page_frame_for(PlotOptions(scale_denominator=10), (6_500_000, 5_500_000)))
    view.fit_to_page()
    position = qc.QPointF(150.25, 180.75)
    anchor = view._scene_under(position)

    for _ in range(4):
        view.zoom_by(2, position)
        assert point_xy(view._scene_under(position)) == pytest.approx(point_xy(anchor), abs=1e-7, rel=0)
        shown = view.viewportTransform().map(anchor)
        assert point_xy(shown) == pytest.approx(point_xy(position), abs=1.5, rel=0)


@pytest.fixture
def layout(app):
    viewer = DxfViewer()
    viewer.resize(1000, 750)
    viewer.show()
    panel = LayoutPanel()
    host = SimpleNamespace(
        dxf_viewer=viewer,
        layout_panel=panel,
        sheets=SheetSet(),
        table_template=default_template(),
        loading=lambda **kwargs: nullcontext(),
    )
    controller = LayoutController(host)
    controller.wire()
    viewer.execute_command(AddLineCommand((6_500_000, 5_500_000), (6_500_025, 5_500_010)))
    app.processEvents()
    controller.activate(0)
    app.processEvents()
    yield controller, host
    viewer.close()
    viewer.deleteLater()
    panel.deleteLater()
    app.processEvents()


def wheel(view, delta, position):
    event = qg.QWheelEvent(
        position, qc.QPointF(), qc.QPoint(), qc.QPoint(0, delta),
        qc.Qt.MouseButton.NoButton, qc.Qt.KeyboardModifier.NoModifier,
        qc.Qt.ScrollPhase.NoScrollPhase, False,
    )
    view.wheelEvent(event)


def test_fractional_wheel_does_not_leak_between_tabs(layout):
    controller, host = layout
    view = host.dxf_viewer.view
    position = qc.QPointF(200, 200)
    wheel(view, 60, position)
    controller.activate(None)
    controller.activate(0)
    before = host.sheets.active

    wheel(view, 60, position)

    assert host.sheets.active == before
    wheel(view, 60, position)
    assert host.sheets.active.options.scale_denominator == 417


@pytest.mark.parametrize("direction", [1, -1])
def test_fractional_wheel_matches_one_complete_notch(layout, direction):
    controller, host = layout
    view = host.dxf_viewer.view
    position = qc.QPointF(170.25, 210.75)
    initial = host.sheets.active
    wheel(view, 120 * direction, position)
    expected = host.sheets.active
    host.sheets.set_options(0, initial.options)
    host.sheets.set_center(0, initial.center)
    controller.reapply()

    for _ in range(8):
        wheel(view, 15 * direction, position)

    assert host.sheets.active == expected


@pytest.mark.parametrize("rotation", [0.0, 35.0])
def test_sheet_zoom_and_tab_roundtrip_preserve_anchor_and_export_frame(layout, rotation):
    controller, host = layout
    view = host.dxf_viewer.view
    host.sheets.set_rotation(0, rotation)
    controller.reapply()
    position = qc.QPointF(170.25, 210.75)
    view.zoom_by(1.7, position)
    anchor = view._to_world(view._scene_under(position))
    wheel(view, 120, position)
    center = view.save_view()[1]
    frame = view._page_frame
    zoom = view.current_zoom_factor()
    assert point_xy(view._to_world(view._scene_under(position))) == pytest.approx(
        point_xy(anchor), abs=1e-7, rel=0,
    )

    for _ in range(3):
        controller.activate(None)
        controller.activate(0)

    assert point_xy(view.save_view()[1]) == pytest.approx(point_xy(center), abs=1e-7, rel=0)
    assert view.current_zoom_factor() == pytest.approx(zoom)
    assert controller.job_for(0).frame == frame


def detail_geometry(view, handle):
    result = []
    for item in view.scene().items():
        if item.data(HANDLE_ROLE) != handle or not item.data(DETAIL_CONTENT_ROLE):
            continue
        rect = item.sceneBoundingRect()
        result.append((rect.x(), rect.y(), rect.width(), rect.height()))
    return sorted(result)


def test_live_detail_zoom_matches_a_fresh_render_on_rotated_sheet(layout):
    controller, host = layout
    viewer = host.dxf_viewer
    command = AddDetailViewCommand(DetailViewSpec(
        center=(6_500_025, 5_500_025), width=20, height=20,
        source=(6_500_005, 5_500_002), scale=2,
    ))
    viewer.execute_command(command)
    host.sheets.set_rotation(0, 35)
    controller.reapply()

    viewer._on_detail_zoom(command.handle, 1.0, 6_500_025, 5_500_025)
    live = detail_geometry(viewer.view, command.handle)
    viewer._commit_detail_gesture()
    controller.activate(None)
    controller.activate(0)
    refreshed = detail_geometry(viewer.view, command.handle)

    assert live
    assert len(live) == len(refreshed)
    for before, after in zip(live, refreshed):
        assert before == pytest.approx(after, abs=1e-7, rel=0)


def test_panning_a_rotated_sheet_matches_export_coordinates(layout, monkeypatch):
    controller, host = layout
    viewer = host.dxf_viewer
    view = viewer.view
    host.sheets.set_rotation(0, 35)
    controller.reapply()
    view.pan_by(5.0, -7.0)
    job = controller.job_for(0)
    item = next(item for item in view.scene().items() if isinstance(item, qw.QGraphicsLineItem))
    preview_start = item.sceneTransform().map(item.line().p1())
    preview_end = item.sceneTransform().map(item.line().p2())
    expected_matrix = content_rotation_matrix(job.frame.rotation, (job.frame.center_x, job.frame.center_y))
    expected_start = expected_matrix.transform((item.line().x1(), item.line().y1(), 0))
    assert point_xy(preview_start) == pytest.approx((expected_start.x, expected_start.y), abs=1e-7, rel=0)

    segments = []

    class Backend:
        def configure(self, config):
            pass

        def set_background(self, color):
            pass

        def draw_line(self, start, end, properties):
            segments.append((start, end))

        def finalize(self):
            pass

    monkeypatch.setattr(pdf_export, "QtPainterBackend", lambda *args: Backend())
    player = pdf_export._record(viewer._doc, render_configuration(job.options)).player().copy()
    player.transform(expected_matrix)
    settings = settings_for(job.options)
    box = pdf_export.job_render_box(job)
    page = pdf_export._final_page(job, settings, box)
    pdf_export._replay(player, None, page, settings, box, paper_stroke_style(job.options))
    sheet = job.frame.sheet_rect()

    def paper_point(point):
        return (
            (point.x() - sheet.left()) / sheet.width() * page.width_in_mm,
            (sheet.bottom() - point.y()) / sheet.height() * page.height_in_mm,
        )

    assert len(segments) == 1
    assert tuple(segments[0][0]) == pytest.approx(paper_point(preview_start), abs=1e-7, rel=0)
    assert tuple(segments[0][1]) == pytest.approx(paper_point(preview_end), abs=1e-7, rel=0)


@pytest.mark.parametrize("rotation", [0.0, 35.0, 90.0, -90.0])
def test_vertical_pan_stays_vertical_on_a_rotated_sheet(layout, rotation):
    controller, host = layout
    view = host.dxf_viewer.view
    host.sheets.set_rotation(0, rotation)
    controller.reapply()
    item = next(item for item in view.scene().items() if isinstance(item, qw.QGraphicsLineItem))
    before = view.viewportTransform().map(item.sceneTransform().map(item.line().p1()))
    old_position = qc.QPointF(300.0, 300.0)
    new_position = qc.QPointF(300.0, 250.0)
    old_scene = view._scene_at(old_position)
    new_scene = view._scene_at(new_position)

    view.pan_by(old_scene.x() - new_scene.x(), old_scene.y() - new_scene.y())

    after = view.viewportTransform().map(item.sceneTransform().map(item.line().p1()))
    assert point_xy(after - before) == pytest.approx((0.0, -50.0), abs=1e-7, rel=0)


@pytest.mark.parametrize("sheet_rotation", [0.0, 35.0, 90.0, -90.0])
def test_vertical_detail_pan_stays_vertical_on_a_rotated_sheet(layout, sheet_rotation):
    controller, host = layout
    viewer = host.dxf_viewer
    view = viewer.view
    viewer.execute_command(AddPointCommand((6_500_012, 5_500_005)))
    command = AddDetailViewCommand(DetailViewSpec(
        center=(6_500_025, 5_500_025), width=30, height=30,
        source=(6_500_012, 5_500_005), scale=1, rotation=27,
    ))
    viewer.execute_command(command)
    host.sheets.set_rotation(0, sheet_rotation)
    controller.reapply()
    item = next(
        item for item in view.scene().items()
        if isinstance(item, PointItem)
        and item.data(HANDLE_ROLE) == command.handle
        and item.data(DETAIL_CONTENT_ROLE)
    )
    before = view.viewportTransform().map(item.sceneTransform().map(item._pos))
    old_position = view.viewportTransform().map(view._to_scene(qc.QPointF(*command.spec.center)))
    new_position = old_position + qc.QPointF(0.0, -40.0)
    old_world = view._world_point(old_position)
    new_world = view._world_point(new_position)

    viewer._on_detail_pan(
        command.handle, new_world.x() - old_world.x(), new_world.y() - old_world.y()
    )

    item = next(
        item for item in view.scene().items()
        if isinstance(item, PointItem)
        and item.data(HANDLE_ROLE) == command.handle
        and item.data(DETAIL_CONTENT_ROLE)
    )
    after = view.viewportTransform().map(item.sceneTransform().map(item._pos))
    assert point_xy(after - before) == pytest.approx((0.0, -40.0), abs=1e-7, rel=0)


def test_editor_refresh_and_tab_switches_preserve_sheet_camera(app, tmp_path, monkeypatch):
    settings = qc.QSettings(str(tmp_path / "settings.ini"), qc.QSettings.Format.IniFormat)
    monkeypatch.setattr(editor_window, "app_settings", lambda: settings)
    window = editor_window.MainWindow(initial_state=ProjectState())
    try:
        window.showNormal()
        app.processEvents()
        viewer = window.dxf_viewer
        viewer.execute_command(AddLineCommand((6_500_000, 5_500_000), (6_500_025, 5_500_010)))
        window.layouts.activate(0)
        app.processEvents()
        position = qc.QPointF(170.25, 210.75)
        viewer.view.zoom_by(1.7, position)
        wheel(viewer.view, 120, position)
        app.processEvents()
        center = viewer.view.save_view()[1]
        zoom = viewer.current_zoom_factor()
        frame = window.layouts.job_for(0).frame

        for _ in range(3):
            window.layouts.activate(None)
            app.processEvents()
            window.layouts.activate(0)
            app.processEvents()

        assert point_xy(viewer.view.save_view()[1]) == pytest.approx(point_xy(center), abs=1e-7, rel=0)
        assert viewer.current_zoom_factor() == pytest.approx(zoom)
        assert window.layouts.job_for(0).frame == frame
        assert viewer.view._page_frame == frame
    finally:
        window.hide()
        window.deleteLater()
        app.processEvents()
