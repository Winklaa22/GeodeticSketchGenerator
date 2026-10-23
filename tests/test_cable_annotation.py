from __future__ import annotations

import pytest

from core.cable_annotation import SlotKind, plan_cable_slots, plan_chain_slots
from models.point import Point


def _line(*xs: float) -> list[Point]:
    return [Point(x=x, y=0.0, h=100.0 + x / 10.0) for x in xs]


def test_marks_are_spread_evenly_and_alternate_with_heights_starting_with_a_mark() -> None:
    slots = plan_chain_slots(_line(*[10.0 * i for i in range(11)]), spacing=20.0, label_width=2.0, clearance=0.5)
    assert [s.kind for s in slots] == [
        SlotKind.MARK, SlotKind.HEIGHT, SlotKind.MARK, SlotKind.HEIGHT, SlotKind.MARK,
    ]
    marks = [s.x for s in slots if s.kind is SlotKind.MARK]
    assert marks == pytest.approx([10.0, 50.0, 90.0], abs=1.5)
    assert all(abs(x - round(x / 10.0) * 10.0) >= 1.5 - 1e-9 for x in marks)


def test_a_height_sits_on_the_cable_right_next_to_a_point_and_carries_its_height() -> None:
    chain = _line(*[10.0 * i for i in range(11)])
    slots = plan_chain_slots(chain, spacing=20.0, label_width=2.0, clearance=0.5)
    for slot in (s for s in slots if s.kind is SlotKind.HEIGHT):
        nearest = min(chain, key=lambda p: abs(p.x - slot.x))
        assert abs(slot.x - nearest.x) == pytest.approx(1.5)
        assert slot.y == pytest.approx(0.0)
        assert slot.h == pytest.approx(nearest.h)


def test_no_height_where_no_point_is_near() -> None:
    slots = plan_chain_slots(_line(0.0, 100.0), spacing=20.0, label_width=2.0, clearance=0.5)
    assert all(s.kind is SlotKind.MARK for s in slots)


def test_a_slot_never_straddles_a_vertex() -> None:
    slots = plan_chain_slots(_line(0.0, 20.0, 40.0), spacing=40.0, label_width=4.0, clearance=1.0)
    assert len(slots) == 1
    assert abs(slots[0].x - 20.0) >= 3.0


def test_segments_too_short_for_a_label_hold_none() -> None:
    assert plan_chain_slots(_line(0.0, 2.0, 4.0), spacing=1.0, label_width=3.0, clearance=0.5) == []


def test_slots_keep_their_separation() -> None:
    slots = plan_chain_slots(_line(0.0, 9.0, 10.0, 30.0), spacing=5.0, label_width=3.0, clearance=0.5)
    xs = [s.x for s in slots]
    assert all(b - a >= 3.5 - 1e-9 for a, b in zip(xs, xs[1:]))


def test_rotation_reads_left_to_right() -> None:
    chain = [Point(x=10.0, y=10.0, h=0.0), Point(x=0.0, y=0.0, h=0.0)]
    slots = plan_chain_slots(chain, spacing=20.0, label_width=1.0, clearance=0.5)
    assert slots[0].rotation == pytest.approx(45.0)


def test_every_chain_starts_with_its_own_mark() -> None:
    slots = plan_cable_slots([_line(0.0, 20.0), _line(100.0, 120.0)], spacing=20.0, label_width=1.0, clearance=0.5)
    assert [s.kind for s in slots] == [SlotKind.MARK, SlotKind.MARK]


def test_neighbouring_labels_keep_the_minimum_gap() -> None:
    chain = _line(*[3.0 * i for i in range(30)])
    slots = plan_chain_slots(chain, spacing=4.0, label_width=1.0, clearance=0.2, min_gap=7.0)
    xs = [s.x for s in slots]
    assert len(xs) >= 2
    assert all(b - a >= 7.0 - 1e-9 for a, b in zip(xs, xs[1:]))
