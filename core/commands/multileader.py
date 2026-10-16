from __future__ import annotations

from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from core.dxf_document import DXFDocument
from core.exceptions import MultileaderError
from core.multileader import (
    MultileaderSpec,
    MultileaderStyle,
    apply_style,
    move_text,
    rescale_spec,
)


class AddMultileaderCommand:
    def __init__(self, spec: MultileaderSpec) -> None:
        self._spec = spec.normalized()
        self.handles: List[str] = []
        self.handle: Optional[str] = None

    @property
    def spec(self) -> MultileaderSpec:
        return self._spec

    def execute(self, doc: DXFDocument) -> None:
        if self.handle is not None:
            doc.relink_entity(self.handle)
            return
        self.handle = doc.add_multileader(self._spec)
        self.handles = [self.handle]

    def undo(self, doc: DXFDocument) -> None:
        if self.handle is not None:
            doc.unlink_entity(self.handle)


class _RebuildMultileadersCommand:
    def __init__(self) -> None:
        self._changes: List[Tuple[str, Any, MultileaderSpec]] = []
        self.handles: List[str] = []

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        raise NotImplementedError

    def execute(self, doc: DXFDocument) -> None:
        if not self._changes:
            for handle, spec in self._specs(doc):
                if not doc.is_multileader(handle):
                    continue
                self._changes.append((handle, doc.snapshot_multileader(handle), spec.normalized()))
                self.handles.append(handle)
        for handle, _snapshot, spec in self._changes:
            doc.rebuild_multileader(handle, spec)

    def undo(self, doc: DXFDocument) -> None:
        for handle, snapshot, _spec in reversed(self._changes):
            doc.restore_multileader(handle, snapshot)


class DefineMultileaderStyleCommand:
    def __init__(self, style: MultileaderStyle) -> None:
        self._style = style.normalized()
        self._previous: Optional[Dict[str, MultileaderStyle]] = None
        self._rebuild: Optional[ApplyMultileaderStyleCommand] = None

    def execute(self, doc: DXFDocument) -> None:
        if not self._style.name:
            raise MultileaderError("Multileader style needs a name")
        styles = doc.multileader_styles()
        if self._previous is None:
            self._previous = dict(styles)
            self._rebuild = ApplyMultileaderStyleCommand(self._style.name, self._style)
        styles[self._style.name] = self._style
        doc.set_multileader_styles(styles)
        assert self._rebuild is not None
        self._rebuild.execute(doc)

    def undo(self, doc: DXFDocument) -> None:
        assert self._previous is not None and self._rebuild is not None
        self._rebuild.undo(doc)
        doc.set_multileader_styles(self._previous)


class DeleteMultileaderStyleCommand:
    def __init__(self, name: str) -> None:
        self._name = name
        self._previous: Optional[Dict[str, MultileaderStyle]] = None

    def execute(self, doc: DXFDocument) -> None:
        if self._name == "Standard":
            raise MultileaderError("The Standard multileader style cannot be deleted")
        if doc.multileader_style_in_use(self._name):
            raise MultileaderError(f"Multileader style {self._name} is in use")
        styles = doc.multileader_styles()
        if self._name not in styles:
            raise MultileaderError(f"Unknown multileader style: {self._name}")
        if self._previous is None:
            self._previous = dict(styles)
        del styles[self._name]
        doc.set_multileader_styles(styles)

    def undo(self, doc: DXFDocument) -> None:
        assert self._previous is not None
        doc.set_multileader_styles(self._previous)


class ApplyMultileaderStyleCommand(_RebuildMultileadersCommand):
    def __init__(
        self, style_name: str, style: Optional[MultileaderStyle] = None, handles: Optional[Sequence[str]] = None
    ) -> None:
        super().__init__()
        self._style_name = style_name
        self._style = style
        self._targets = list(handles) if handles is not None else None

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        style = self._style or doc.multileader_styles().get(self._style_name)
        if style is None:
            raise MultileaderError(f"Unknown multileader style: {self._style_name}")
        if self._targets is None:
            targets = doc.multileaders_using_style(self._style_name)
        else:
            targets = [handle for handle in dict.fromkeys(self._targets) if doc.is_multileader(handle)]
        result: List[Tuple[str, MultileaderSpec]] = []
        for handle in targets:
            spec = doc.multileader_spec(handle)
            if spec is not None:
                result.append((handle, apply_style(spec, style)))
        return result


class RescaleAnnotativeCommand(_RebuildMultileadersCommand):
    def __init__(self, scale: float) -> None:
        super().__init__()
        self._scale = scale

    def has_changes(self, doc: DXFDocument) -> bool:
        return bool(self._specs(doc))

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        styles = doc.multileader_styles()
        result: List[Tuple[str, MultileaderSpec]] = []
        for entity in doc.modelspace:
            if entity.dxftype() != "MULTILEADER":
                continue
            spec = doc.multileader_spec(entity.dxf.handle)
            style = styles.get(spec.style_name) if spec is not None else None
            if style is not None and style.annotative and spec.scale != self._scale:
                result.append((entity.dxf.handle, rescale_spec(spec, self._scale)))
        return result


class MoveMultileaderGripCommand(_RebuildMultileadersCommand):
    def __init__(self, handle: str, grip: str, point: Tuple[float, float]) -> None:
        super().__init__()
        self._handle = handle
        self._grip = grip
        self._point = (float(point[0]), float(point[1]))

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        spec = doc.multileader_spec(self._handle)
        if spec is None:
            raise MultileaderError("Not a multileader")
        if self._grip == "tip":
            spec = replace(spec, tip=self._point)
        elif self._grip == "landing":
            spec = replace(spec, landing=self._point, landing_length=0.0)
        elif self._grip == "text":
            spec = move_text(spec, self._point)
        return [(self._handle, spec)]


class EditMultileaderTextCommand(_RebuildMultileadersCommand):
    def __init__(self, handle: str, text: str) -> None:
        super().__init__()
        self._handle = handle
        self._text = text

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        spec = doc.multileader_spec(self._handle)
        if spec is None:
            raise MultileaderError("Not a multileader")
        return [(self._handle, replace(spec, text=self._text))]


class SetMultileaderPropertiesCommand(_RebuildMultileadersCommand):
    def __init__(self, handles: Sequence[str], **changes: Any) -> None:
        super().__init__()
        self._targets = list(dict.fromkeys(handles))
        self._properties = changes

    def _specs(self, doc: DXFDocument) -> List[Tuple[str, MultileaderSpec]]:
        result: List[Tuple[str, MultileaderSpec]] = []
        for handle in self._targets:
            spec = doc.multileader_spec(handle)
            if spec is not None:
                result.append((handle, replace(spec, **self._properties)))
        if not result:
            raise MultileaderError("Not a multileader")
        return result
