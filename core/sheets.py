from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields, replace
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from core.plot import PlotOptions
from core.project import LayoutState, SheetState

SHEET_NAME_PREFIX = "Sheet"


@dataclass(frozen=True)
class Sheet:
    name: str
    options: PlotOptions = PlotOptions()
    center: Optional[Tuple[float, float]] = None
    rotation: float = 0.0
    field_values: Dict[str, str] = field(default_factory=dict)


def options_from_state(state: SheetState) -> PlotOptions:
    names = {field.name for field in fields(PlotOptions)}
    return PlotOptions(**{key: value for key, value in asdict(state).items() if key in names})


def sheet_from_state(state: SheetState) -> Sheet:
    center = None
    if state.center_x is not None and state.center_y is not None:
        center = (state.center_x, state.center_y)
    return Sheet(
        name=state.name,
        options=options_from_state(state),
        center=center,
        rotation=state.rotation,
        field_values=dict(state.field_values),
    )


def state_from_sheet(sheet: Sheet) -> SheetState:
    center_x, center_y = sheet.center if sheet.center is not None else (None, None)
    return SheetState(
        name=sheet.name,
        center_x=center_x,
        center_y=center_y,
        rotation=sheet.rotation,
        field_values=dict(sheet.field_values),
        **asdict(sheet.options),
    )


def unique_name(name: str, taken: Iterable[str]) -> str:
    existing = set(taken)
    if name not in existing:
        return name
    index = 2
    while f"{name} ({index})" in existing:
        index += 1
    return f"{name} ({index})"


def next_sheet_name(taken: Iterable[str]) -> str:
    existing = set(taken)
    index = 1
    while f"{SHEET_NAME_PREFIX} {index}" in existing:
        index += 1
    return f"{SHEET_NAME_PREFIX} {index}"


class SheetSet:

    def __init__(
        self,
        sheets: Optional[Sequence[Sheet]] = None,
        active_index: Optional[int] = None,
    ) -> None:
        if sheets is None:
            sheets = [Sheet(name=f"{SHEET_NAME_PREFIX} 1")]
        self._sheets: List[Sheet] = list(sheets)
        self._active: Optional[int] = None
        self._model_rotation = 0.0
        self._model_zoom = 1.0
        self._model_center: Optional[Tuple[float, float]] = None
        self.activate(active_index)

    def __len__(self) -> int:
        return len(self._sheets)

    @property
    def sheets(self) -> Tuple[Sheet, ...]:
        return tuple(self._sheets)

    def names(self) -> List[str]:
        return [sheet.name for sheet in self._sheets]

    def at(self, index: int) -> Sheet:
        return self._sheets[index]

    @property
    def active_index(self) -> Optional[int]:
        return self._active

    @property
    def active(self) -> Optional[Sheet]:
        return self._sheets[self._active] if self._active is not None else None

    def activate(self, index: Optional[int]) -> None:
        self._active = index if index is not None and 0 <= index < len(self._sheets) else None

    def add(self, options: Optional[PlotOptions] = None, activate: bool = True) -> int:
        self._sheets.append(
            Sheet(name=next_sheet_name(self.names()), options=options or PlotOptions())
        )
        index = len(self._sheets) - 1
        if activate:
            self._active = index
        return index

    def duplicate(self, index: int, activate: bool = True) -> int:
        source = self._sheets[index]
        self._sheets.insert(
            index + 1, replace(source, name=unique_name(source.name, self.names()))
        )
        if self._active is not None and self._active > index:
            self._active += 1
        if activate:
            self._active = index + 1
        return index + 1

    def rename(self, index: int, name: str) -> str:
        cleaned = name.strip() or self._sheets[index].name
        taken = [other for position, other in enumerate(self.names()) if position != index]
        applied = unique_name(cleaned, taken)
        self._sheets[index] = replace(self._sheets[index], name=applied)
        return applied

    def delete(self, index: int) -> None:
        del self._sheets[index]
        if self._active is None:
            return
        if self._active == index:
            self.activate(min(index, len(self._sheets) - 1) if self._sheets else None)
        elif self._active > index:
            self._active -= 1

    def move(self, index: int, new_index: int) -> int:
        new_index = max(0, min(new_index, len(self._sheets) - 1))
        if new_index == index:
            return index
        active = self._active
        self._sheets.insert(new_index, self._sheets.pop(index))
        if active is not None:
            if active == index:
                self._active = new_index
            elif index < active <= new_index:
                self._active = active - 1
            elif new_index <= active < index:
                self._active = active + 1
        return new_index

    def set_options(self, index: int, options: PlotOptions) -> None:
        self._sheets[index] = replace(self._sheets[index], options=options)

    def set_center(self, index: int, center: Optional[Tuple[float, float]]) -> None:
        self._sheets[index] = replace(self._sheets[index], center=center)

    def set_rotation(self, index: int, rotation: float) -> None:
        self._sheets[index] = replace(self._sheets[index], rotation=rotation)

    def set_field_values(self, index: int, values: Dict[str, str]) -> None:
        self._sheets[index] = replace(self._sheets[index], field_values=values)

    @property
    def model_rotation(self) -> float:
        return self._model_rotation

    def set_model_rotation(self, rotation: float) -> None:
        self._model_rotation = float(rotation)

    @property
    def model_zoom(self) -> float:
        return self._model_zoom

    @property
    def model_center(self) -> Optional[Tuple[float, float]]:
        return self._model_center

    def set_model_view(self, zoom: float, center: Optional[Tuple[float, float]]) -> None:
        """Remember the Model tab's camera - its zoom relative to the fit, and pan."""
        self._model_zoom = float(zoom) if zoom > 0 else 1.0
        self._model_center = (float(center[0]), float(center[1])) if center is not None else None

    def to_state(self) -> LayoutState:
        return LayoutState(
            sheets=[state_from_sheet(sheet) for sheet in self._sheets],
            active_index=self._active,
            model_rotation=self._model_rotation,
            model_zoom=self._model_zoom,
            model_center=self._model_center,
        )

    def load_state(self, state: LayoutState) -> None:
        self._sheets = [sheet_from_state(item) for item in state.sheets]
        self._model_rotation = float(state.model_rotation)
        self._model_zoom = state.model_zoom if state.model_zoom > 0 else 1.0
        self._model_center = tuple(state.model_center) if state.model_center is not None else None
        self.activate(state.active_index)

    @classmethod
    def from_state(cls, state: LayoutState) -> "SheetSet":
        instance = cls()
        instance.load_state(state)
        return instance
