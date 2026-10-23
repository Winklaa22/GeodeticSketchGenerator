from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional, Sequence, Tuple

from core.geometry import compute_direction_angle, snap_small_rotation
from models.point import Point

Interval = Tuple[float, float, int]


class SlotKind(Enum):
    MARK = "mark"
    HEIGHT = "height"


@dataclass(frozen=True)
class CableSlot:
    kind: SlotKind
    x: float
    y: float
    h: float
    rotation: float


def _cumulative_lengths(chain: Sequence[Point]) -> List[float]:
    stations = [0.0]
    for a, b in zip(chain, chain[1:]):
        stations.append(stations[-1] + math.hypot(b.x - a.x, b.y - a.y))
    return stations


def _admissible_intervals(stations: Sequence[float], margin: float) -> List[Interval]:
    intervals: List[Interval] = []
    for j in range(len(stations) - 1):
        lo, hi = stations[j] + margin, stations[j + 1] - margin
        if lo <= hi:
            intervals.append((lo, hi, j))
    return intervals


def _snap_mark(target: float, lower: float, intervals: Sequence[Interval]) -> Optional[Tuple[float, int, int]]:
    best: Optional[Tuple[float, int, int]] = None
    for lo, hi, j in intervals:
        if hi < lower:
            continue
        s = min(max(target, lo, lower), hi)
        if best is None or abs(s - target) < abs(best[0] - target):
            best = (s, j, -1)
    return best


def _snap_height(target: float, lower: float, intervals: Sequence[Interval]) -> Optional[Tuple[float, int, int]]:
    best: Optional[Tuple[float, int, int]] = None
    for lo, hi, j in intervals:
        for s, vertex in ((lo, j), (hi, j + 1)):
            if s < lower:
                continue
            if best is None or abs(s - target) < abs(best[0] - target):
                best = (s, j, vertex)
    return best


def _slot_at(
    chain: Sequence[Point], stations: Sequence[float], s: float, j: int, vertex: int, kind: SlotKind
) -> CableSlot:
    a, b = chain[j], chain[j + 1]
    length = stations[j + 1] - stations[j]
    t = (s - stations[j]) / length
    angle_deg = compute_direction_angle(a, b)
    h = chain[vertex].h if vertex >= 0 else a.h + t * (b.h - a.h)
    return CableSlot(
        kind=kind,
        x=a.x + t * (b.x - a.x),
        y=a.y + t * (b.y - a.y),
        h=h,
        rotation=snap_small_rotation(angle_deg, round(angle_deg, 1)),
    )


def plan_chain_slots(
    chain: Sequence[Point], spacing: float, label_width: float, clearance: float, min_gap: float = 0.0
) -> List[CableSlot]:
    if len(chain) < 2 or spacing <= 0.0:
        return []
    stations = _cumulative_lengths(chain)
    total = stations[-1]
    intervals = _admissible_intervals(stations, label_width / 2.0 + clearance)
    if total <= 0.0 or not intervals:
        return []
    count = max(1, round(total / spacing))
    step = total / count
    separation = max(label_width + clearance, min_gap)
    slots: List[CableSlot] = []
    last = -math.inf
    for k in range(count):
        kind = SlotKind.MARK if k % 2 == 0 else SlotKind.HEIGHT
        target = (k + 0.5) * step
        snap = _snap_mark if kind is SlotKind.MARK else _snap_height
        snapped = snap(target, last + separation, intervals)
        if snapped is None or abs(snapped[0] - target) > step / 2.0:
            continue
        s, j, vertex = snapped
        slots.append(_slot_at(chain, stations, s, j, vertex, kind))
        last = s
    return slots


def plan_cable_slots(
    chains: Sequence[Sequence[Point]], spacing: float, label_width: float, clearance: float, min_gap: float = 0.0
) -> List[CableSlot]:
    slots: List[CableSlot] = []
    for chain in chains:
        slots.extend(plan_chain_slots(chain, spacing, label_width, clearance, min_gap))
    return slots
