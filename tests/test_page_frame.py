from __future__ import annotations

from core.plot import PlotOptions
from ui.dxf.page_frame import PageFrame, page_frame_for
from ui.dxf.pdf_export import PlotJob, export_sheets, job_render_box

A3 = PlotOptions(page_key="a3", landscape=True, scale_denominator=500, margin_mm=10.0)


def test_page_frame_for_sizes_the_sheet_in_model_units() -> None:
    frame = page_frame_for(A3, (0.0, 0.0))
    rect = frame.sheet_rect()
    assert (rect.width(), rect.height()) == (210.0, 148.5)
    assert (rect.center().x(), rect.center().y()) == (0.0, 0.0)


def test_page_frame_for_carries_the_centre_and_label() -> None:
    frame = page_frame_for(A3, (100.0, -50.0), "Sytuacja")
    assert (frame.center_x, frame.center_y) == (100.0, -50.0)
    assert frame.label == "Sytuacja"
    assert frame.sheet_rect().center().x() == 100.0


def test_printable_rect_insets_by_the_margin() -> None:
    printable = page_frame_for(A3, (0.0, 0.0)).printable_rect()
    assert (printable.width(), printable.height()) == (200.0, 138.5)


def test_printable_rect_never_inverts_on_an_oversized_margin() -> None:
    frame = PageFrame(center_x=0.0, center_y=0.0, width=10.0, height=6.0, margin=99.0)
    printable = frame.printable_rect()
    assert printable.width() >= 0.0
    assert printable.height() >= 0.0


def test_moved_to_shifts_the_sheet_and_keeps_its_size() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), "Sheet 1").moved_to(25.0, -75.0)
    assert (frame.center_x, frame.center_y) == (25.0, -75.0)
    assert frame.label == "Sheet 1"
    assert frame.sheet_rect().width() == 210.0


def test_page_frame_for_defaults_to_no_rotation() -> None:
    assert page_frame_for(A3, (0.0, 0.0)).rotation == 0.0


def test_page_frame_for_normalizes_a_carried_rotation() -> None:
    assert page_frame_for(A3, (0.0, 0.0), rotation=200.0).rotation == -160.0


def test_rotated_to_updates_only_the_rotation() -> None:
    frame = page_frame_for(A3, (10.0, 20.0), "Sheet 1").rotated_to(30.0)
    assert frame.rotation == 30.0
    assert (frame.center_x, frame.center_y) == (10.0, 20.0)
    assert frame.sheet_rect().width() == 210.0


def test_rotated_to_normalizes_the_stored_angle() -> None:
    frame = page_frame_for(A3, (0.0, 0.0)).rotated_to(400.0)
    assert frame.rotation == 40.0


def test_rotated_to_does_not_change_the_axis_aligned_sheet_rect() -> None:
    unrotated = page_frame_for(A3, (0.0, 0.0))
    rotated = unrotated.rotated_to(35.0)
    assert rotated.sheet_rect() == unrotated.sheet_rect()
    assert rotated.printable_rect() == unrotated.printable_rect()


def test_job_render_box_matches_the_frame_the_preview_draws() -> None:
    frame = page_frame_for(A3, (100.0, -50.0), "Sytuacja")
    box = job_render_box(PlotJob("Sytuacja", A3, frame))
    rect = frame.sheet_rect()
    assert (box.extmin.x, box.extmin.y) == (rect.left(), rect.top())
    assert (box.extmax.x, box.extmax.y) == (rect.right(), rect.bottom())


def test_job_render_box_follows_a_moved_sheet() -> None:
    moved = page_frame_for(A3, (0.0, 0.0)).moved_to(400.0, 300.0)
    box = job_render_box(PlotJob("Sheet 1", A3, moved))
    assert ((box.extmin.x + box.extmax.x) / 2, (box.extmin.y + box.extmax.y) / 2) == (400.0, 300.0)


def test_export_sheets_reports_when_there_is_nothing_to_plot() -> None:
    ok, message = export_sheets(None, "unused.pdf", [])
    assert not ok
    assert "no sheets" in message.lower()


def test_page_frame_for_defaults_to_no_table_when_height_is_omitted() -> None:
    frame = page_frame_for(A3, (0.0, 0.0))
    assert frame.table_height == 0.0
    assert frame.map_rect() == frame.printable_rect()


def test_page_frame_for_zero_table_height_degenerates_to_the_old_behaviour() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=0.0)
    assert frame.map_rect() == frame.printable_rect()
    assert frame.table_rect().height() == 0.0


def test_map_rect_carves_the_table_off_the_visual_bottom() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=30.0)
    printable = frame.printable_rect()
    map_rect = frame.map_rect()
    assert map_rect.bottom() == printable.bottom()
    assert map_rect.top() > printable.top()
    assert map_rect.width() == printable.width()


def test_table_rect_is_the_complement_of_map_rect() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=30.0)
    printable = frame.printable_rect()
    map_rect = frame.map_rect()
    table_rect = frame.table_rect()
    assert table_rect.top() == printable.top()
    assert table_rect.bottom() == map_rect.top()
    assert table_rect.width() == printable.width()
    assert abs(table_rect.height() - (printable.height() - map_rect.height())) < 1e-9


def test_table_rect_defaults_to_full_width_when_no_cap_is_given() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=30.0)
    assert frame.table_rect().width() == frame.printable_rect().width()


def test_table_rect_caps_the_width_and_stays_left_anchored() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=30.0, table_width_mm=50.0)
    printable = frame.printable_rect()
    table_rect = frame.table_rect()
    assert table_rect.left() == printable.left()
    assert table_rect.width() == 50.0 * 0.5  # scaled by units_per_mm (scale_denominator=500)


def test_table_rect_width_cap_never_widens_a_narrower_table() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=30.0, table_width_mm=100000.0)
    assert frame.table_rect().width() == frame.printable_rect().width()


def test_table_rect_clamps_when_taller_than_the_printable_area() -> None:
    frame = page_frame_for(A3, (0.0, 0.0), table_height_mm=100000.0)
    printable = frame.printable_rect()
    map_rect = frame.map_rect()
    table_rect = frame.table_rect()
    assert map_rect.height() == 0.0
    assert abs(table_rect.height() - printable.height()) < 1e-9
