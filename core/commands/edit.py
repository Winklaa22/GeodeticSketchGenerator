"""Editing commands — section 2 of the DXF edit command spec (delete, move,
duplicate, rotate, scale; vertex-edit/change-layer are later phases)."""
from __future__ import annotations

from typing import Iterable, List, Sequence

from ezdxf.entities import DXFGraphic

from core.dxf_document import DXFDocument


class DeleteEntityCommand:
    """Deletes one or more entities. Reversible: entities are unlinked (kept
    alive in the entity database) rather than destroyed, so undo restores the
    exact same objects — see `DXFDocument.unlink_entity`/`restore_entity`.

    A handle can go stale between execute() calls (e.g. undoing this command
    and the command that created that same entity, then redoing both — the
    redone creation makes a fresh entity/handle, not the original one this
    command still names) — `unlink_entity` reports that with None rather
    than raising, and it's simply skipped here instead of un-deleted.
    """

    def __init__(self, handles: Iterable[str]) -> None:
        self._handles: List[str] = list(handles)
        self._removed: List[DXFGraphic] = []

    def execute(self, doc: DXFDocument) -> None:
        unlinked = (doc.unlink_entity(handle) for handle in self._handles)
        self._removed = [entity for entity in unlinked if entity is not None]

    def undo(self, doc: DXFDocument) -> None:
        for entity in self._removed:
            doc.restore_entity(entity)
        self._removed = []


class MoveCommand:
    """Translates one or more entities by (dx, dy, dz). Self-inverse — undo
    just translates back by the negated vector, no snapshot needed since
    `DXFDocument.translate_entity` is exact and reversible."""

    def __init__(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> None:
        self._handles: List[str] = list(handles)
        self._dx = dx
        self._dy = dy
        self._dz = dz

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.translate_entity(handle, self._dx, self._dy, self._dz)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.translate_entity(handle, -self._dx, -self._dy, -self._dz)


class DuplicateEntitiesCommand:
    """Copies one or more entities, offsetting the copies by (dx, dy) so
    they land next to the originals rather than exactly on top of them —
    used for Ctrl+D (duplicate) and Ctrl+V (paste). The *first* execute()
    creates the copies and remembers their handles (see `new_handles`); a
    later execute() (a redo) relinks those same handles instead of
    duplicating the sources again — same idiom as the Add*Command classes
    in core.commands.draw, and for the same reason (a redo that instead
    made fresh copies would leave any other Command still naming one of
    the old handles, e.g. a DeleteEntityCommand, pointing at nothing)."""

    def __init__(self, handles: Iterable[str], dx: float, dy: float, dz: float = 0.0) -> None:
        self._handles: List[str] = list(handles)
        self._dx = dx
        self._dy = dy
        self._dz = dz
        self.new_handles: List[str] = []

    def execute(self, doc: DXFDocument) -> None:
        if self.new_handles:
            for handle in self.new_handles:
                doc.relink_entity(handle)
        else:
            self.new_handles = [
                doc.duplicate_entity(handle, self._dx, self._dy, self._dz) for handle in self._handles
            ]

    def undo(self, doc: DXFDocument) -> None:
        for handle in self.new_handles:
            doc.unlink_entity(handle)


class RotateCommand:
    """Rotates one or more entities by `angle` degrees around `center`.
    Self-inverse — undo rotates back by the negated angle around the same
    center, same idea as MoveCommand."""

    def __init__(self, handles: Iterable[str], angle: float, center: Sequence[float]) -> None:
        self._handles: List[str] = list(handles)
        self._angle = angle
        self._center = center

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.rotate_entity(handle, self._angle, self._center)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.rotate_entity(handle, -self._angle, self._center)


class ScaleCommand:
    """Scales one or more entities by `factor` around `center`. Self-inverse
    — undo scales back by 1/factor around the same center, same idea as
    MoveCommand/RotateCommand."""

    def __init__(self, handles: Iterable[str], factor: float, center: Sequence[float]) -> None:
        self._handles: List[str] = list(handles)
        self._factor = factor
        self._center = center

    def execute(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.scale_entity(handle, self._factor, self._center)

    def undo(self, doc: DXFDocument) -> None:
        for handle in self._handles:
            doc.scale_entity(handle, 1.0 / self._factor, self._center)
