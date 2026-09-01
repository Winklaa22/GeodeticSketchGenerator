from __future__ import annotations

from core.plot import PlotOptions
from core.project import LayoutState, SheetState
from core.sheets import (
    Sheet,
    SheetSet,
    next_sheet_name,
    options_from_state,
    sheet_from_state,
    state_from_sheet,
    unique_name,
)


def test_a_fresh_set_holds_one_sheet_in_model_space() -> None:
    sheets = SheetSet()
    assert sheets.names() == ["Sheet 1"]
    assert sheets.active_index is None
    assert sheets.active is None


def test_a_fresh_set_serialises_to_the_default_layout_state() -> None:
    assert SheetSet().to_state() == LayoutState()


def test_unique_name_suffixes_only_on_collision() -> None:
    assert unique_name("Sheet 1", []) == "Sheet 1"
    assert unique_name("Sheet 1", ["Sheet 1"]) == "Sheet 1 (2)"
    assert unique_name("Sheet 1", ["Sheet 1", "Sheet 1 (2)"]) == "Sheet 1 (3)"


def test_next_sheet_name_fills_the_first_free_number() -> None:
    assert next_sheet_name([]) == "Sheet 1"
    assert next_sheet_name(["Sheet 1", "Sheet 3"]) == "Sheet 2"
    assert next_sheet_name(["Sheet 1", "Sheet 2"]) == "Sheet 3"


def test_add_appends_a_uniquely_named_sheet_and_activates_it() -> None:
    sheets = SheetSet()
    index = sheets.add()
    assert index == 1
    assert sheets.names() == ["Sheet 1", "Sheet 2"]
    assert sheets.active_index == 1


def test_add_can_carry_plot_options() -> None:
    sheets = SheetSet()
    options = PlotOptions(page_key="a1", landscape=False, scale_denominator=250)
    sheets.add(options)
    assert sheets.at(1).options == options


def test_duplicate_inserts_after_the_source_with_a_free_name() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.activate(None)
    index = sheets.duplicate(0)
    assert index == 1
    assert sheets.names() == ["Sheet 1", "Sheet 1 (2)", "Sheet 2"]
    assert sheets.at(1).options == sheets.at(0).options


def test_duplicate_shifts_a_later_active_sheet() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.activate(1)
    sheets.duplicate(0, activate=False)
    assert sheets.names() == ["Sheet 1", "Sheet 1 (2)", "Sheet 2"]
    assert sheets.active.name == "Sheet 2"


def test_rename_applies_the_new_name() -> None:
    sheets = SheetSet()
    assert sheets.rename(0, "  Situace  ") == "Situace"
    assert sheets.names() == ["Situace"]


def test_rename_keeps_names_unique() -> None:
    sheets = SheetSet()
    sheets.add()
    assert sheets.rename(1, "Sheet 1") == "Sheet 1 (2)"
    assert sheets.names() == ["Sheet 1", "Sheet 1 (2)"]


def test_rename_to_its_own_name_is_not_treated_as_a_collision() -> None:
    sheets = SheetSet()
    assert sheets.rename(0, "Sheet 1") == "Sheet 1"


def test_rename_to_blank_keeps_the_current_name() -> None:
    sheets = SheetSet()
    assert sheets.rename(0, "   ") == "Sheet 1"


def test_delete_moves_activation_to_the_neighbour() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.add()
    sheets.activate(2)
    sheets.delete(2)
    assert sheets.names() == ["Sheet 1", "Sheet 2"]
    assert sheets.active_index == 1


def test_delete_before_the_active_sheet_shifts_activation_down() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.activate(1)
    sheets.delete(0)
    assert sheets.active.name == "Sheet 2"


def test_deleting_the_last_sheet_falls_back_to_model_space() -> None:
    sheets = SheetSet()
    sheets.activate(0)
    sheets.delete(0)
    assert len(sheets) == 0
    assert sheets.active_index is None
    assert sheets.active is None


def test_move_reorders_and_follows_the_active_sheet() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.add()
    sheets.activate(0)
    assert sheets.move(0, 2) == 2
    assert sheets.names() == ["Sheet 2", "Sheet 3", "Sheet 1"]
    assert sheets.active.name == "Sheet 1"


def test_move_shifts_an_untouched_active_sheet() -> None:
    sheets = SheetSet()
    sheets.add()
    sheets.add()
    sheets.activate(2)
    sheets.move(0, 1)
    assert sheets.active.name == "Sheet 3"
    sheets.activate(0)
    sheets.move(2, 0)
    assert sheets.active.name == "Sheet 2"


def test_move_clamps_out_of_range_targets() -> None:
    sheets = SheetSet()
    sheets.add()
    assert sheets.move(0, 99) == 1
    assert sheets.names() == ["Sheet 2", "Sheet 1"]


def test_activate_ignores_an_out_of_range_index() -> None:
    sheets = SheetSet()
    sheets.activate(7)
    assert sheets.active_index is None


def test_set_options_and_center_replace_the_sheet_in_place() -> None:
    sheets = SheetSet()
    options = PlotOptions(page_key="a2", scale_denominator=2000)
    sheets.set_options(0, options)
    sheets.set_center(0, (12.5, -8.0))
    assert sheets.at(0) == Sheet(name="Sheet 1", options=options, center=(12.5, -8.0))


def test_a_fresh_sheet_has_no_rotation() -> None:
    assert SheetSet().at(0).rotation == 0.0


def test_set_rotation_replaces_the_sheet_in_place() -> None:
    sheets = SheetSet()
    sheets.set_rotation(0, 42.5)
    assert sheets.at(0) == Sheet(name="Sheet 1", rotation=42.5)


def test_rotation_survives_a_state_round_trip() -> None:
    sheet = Sheet(name="Detail", rotation=-15.0)
    assert sheet_from_state(state_from_sheet(sheet)) == sheet


def test_options_survive_a_state_round_trip() -> None:
    options = PlotOptions(
        page_key="a0",
        landscape=False,
        scale_mode="fit",
        scale_denominator=1250,
        margin_mm=7.5,
        color_mode="monochrome",
        min_lineweight_mm=0.25,
    )
    sheet = Sheet(name="Detail", options=options, center=(100.0, -250.0))
    assert sheet_from_state(state_from_sheet(sheet)) == sheet


def test_a_sheet_without_a_centre_round_trips_as_unset() -> None:
    sheet = Sheet(name="Sheet 1")
    state = state_from_sheet(sheet)
    assert state.center_x is None and state.center_y is None
    assert sheet_from_state(state).center is None


def test_options_from_state_ignores_the_non_option_fields() -> None:
    state = SheetState(name="Detail", center_x=1.0, center_y=2.0, page_key="a3")
    assert options_from_state(state) == PlotOptions(page_key="a3")


def test_the_whole_set_survives_a_state_round_trip() -> None:
    sheets = SheetSet()
    sheets.add(PlotOptions(page_key="a1", color_mode="monochrome"))
    sheets.rename(1, "Detail")
    sheets.set_center(1, (5.0, 6.0))
    sheets.activate(1)
    restored = SheetSet.from_state(sheets.to_state())
    assert restored.sheets == sheets.sheets
    assert restored.active_index == 1


def test_load_state_drops_an_out_of_range_active_index() -> None:
    sheets = SheetSet.from_state(LayoutState(sheets=[SheetState()], active_index=4))
    assert sheets.active_index is None


def test_load_state_accepts_an_empty_sheet_list() -> None:
    sheets = SheetSet.from_state(LayoutState(sheets=[], active_index=None))
    assert len(sheets) == 0
    assert sheets.names() == []
