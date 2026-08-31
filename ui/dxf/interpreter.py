from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Tuple

from core.commands.composite import CompositeCommand
from core.commands.draw import AddCircleCommand, AddLineCommand, AddPointCommand
from ui.dxf.tools import (
    CircleToolSession,
    LineToolSession,
    PipeToolSession,
    PointToolSession,
    TextToolSession,
    offset_segment_perpendicular,
    parse_coordinate,
)

if TYPE_CHECKING:
    from ui.dxf.viewer import DxfViewer


class _CommandError(Exception):
    pass


class DxfCommandInterpreter:

    def __init__(self, dxf_viewer: "DxfViewer") -> None:
        self._viewer = dxf_viewer
        self._view = dxf_viewer.view
        self._last_command: Optional[str] = None
        self._commands = {
            "ZOOM": self._cmd_zoom,
            "Z": self._cmd_zoom,
            "PAN": self._cmd_pan,
            "P": self._cmd_pan,
            "REGEN": self._cmd_regen,
            "RE": self._cmd_regen,
            "REDRAW": self._cmd_regen,
            "POINT": self._cmd_point,
            "PO": self._cmd_point,
            "TEXT": self._cmd_text,
            "T": self._cmd_text,
            "LINE": self._cmd_line,
            "L": self._cmd_line,
            "CIRCLE": self._cmd_circle,
            "C": self._cmd_circle,
            "PIPE": self._cmd_pipe,
            "RURA": self._cmd_pipe,
            "RU": self._cmd_pipe,
            "MOVE": self._cmd_move,
            "M": self._cmd_move,
            "ROTATE": self._cmd_rotate,
            "RO": self._cmd_rotate,
            "SCALE": self._cmd_scale,
            "SC": self._cmd_scale,
            "ROTATEEACH": self._cmd_rotate_each,
            "ROE": self._cmd_rotate_each,
            "SCALEEACH": self._cmd_scale_each,
            "SE": self._cmd_scale_each,
            "SELECTSIMILAR": self._cmd_select_similar,
            "SS": self._cmd_select_similar,
            "ERASE": self._cmd_erase,
            "DELETE": self._cmd_erase,
            "E": self._cmd_erase,
            "U": self._cmd_undo,
            "UNDO": self._cmd_undo,
            "REDO": self._cmd_redo,
        }

    def run(self, text: str) -> str:
        text = text.strip()
        if not text:
            if self._last_command is None:
                return ""
            text = self._last_command
        name, *args = text.split()
        handler = self._commands.get(name.upper())
        if handler is None:
            return f'Unknown command "{name}". Press F1 for help.'
        self._last_command = text
        try:
            return handler(args)
        except _CommandError as exc:
            return str(exc)

    def _cmd_zoom(self, args: List[str]) -> str:
        if not args:
            return "Specify a scale factor, or [Extents/Window]:"
        keyword = args[0].upper()
        if keyword in ("E", "EXTENTS", "A", "ALL"):
            self._view.fit_to_scene()
            return ""
        if keyword in ("W", "WINDOW"):
            p1, p2 = self._parse_points(args[1:], count=2)
            if not self._view.zoom_window(p1, p2):
                raise _CommandError("Invalid zoom window.")
            return ""
        if keyword == "IN":
            return "" if self._view.zoom_by(1.25) else "Zoom limit reached."
        if keyword == "OUT":
            return "" if self._view.zoom_by(0.8) else "Zoom limit reached."
        factor = self._parse_factor(args[0])
        return "" if self._view.zoom_by(factor) else "Zoom limit reached."

    def _cmd_pan(self, args: List[str]) -> str:
        if not args:
            return "Click and drag with the left mouse button to pan, or use PAN dx,dy."
        dx, dy = self._parse_point(args[0])
        self._view.pan_by(dx, dy)
        return ""

    def _cmd_regen(self, args: List[str]) -> str:
        return "Regenerating model."

    def _cmd_point(self, args: List[str]) -> str:
        if args:
            coord = parse_coordinate(args[0], last_point=None)
            if coord is None:
                raise _CommandError(f'Point must be given as "x,y": "{args[0]}".')
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddPointCommand(coord, doc.active_layer))
            return ""
        self._viewer.start_tool(PointToolSession())
        return ""

    def _cmd_text(self, args: List[str]) -> str:
        self._viewer.start_tool(TextToolSession())
        return ""

    def _cmd_line(self, args: List[str]) -> str:
        if len(args) >= 2:
            start = parse_coordinate(args[0], last_point=None)
            end = parse_coordinate(args[1], last_point=start)
            if start is None or end is None:
                raise _CommandError(f'Points must be given as "x,y": "{args[0]} {args[1]}".')
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddLineCommand(start, end, doc.active_layer))
            return ""
        self._viewer.start_tool(LineToolSession())
        return ""

    def _cmd_circle(self, args: List[str]) -> str:
        if len(args) >= 2:
            center = parse_coordinate(args[0], last_point=None)
            if center is None:
                raise _CommandError(f'Point must be given as "x,y": "{args[0]}".')
            try:
                radius = float(args[1])
            except ValueError:
                raise _CommandError(f'Requires a numeric radius: "{args[1]}".') from None
            if radius <= 0:
                raise _CommandError("Radius must be positive.")
            doc = self._viewer.ensure_document()
            self._viewer.execute_command(AddCircleCommand(center, radius, doc.active_layer))
            return ""
        self._viewer.start_tool(CircleToolSession())
        return ""

    def _cmd_pipe(self, args: List[str]) -> str:
        if len(args) >= 3:
            start = parse_coordinate(args[0], last_point=None)
            end = parse_coordinate(args[1], last_point=start)
            if start is None or end is None:
                raise _CommandError(f'Points must be given as "x,y": "{args[0]} {args[1]}".')
            try:
                width = float(args[2])
            except ValueError:
                raise _CommandError(f'Requires a numeric width: "{args[2]}".') from None
            if width <= 0:
                raise _CommandError("Width must be positive.")
            doc = self._viewer.ensure_document()
            half = width / 2.0
            line_a = offset_segment_perpendicular(start, end, half)
            line_b = offset_segment_perpendicular(start, end, -half)
            self._viewer.execute_command(
                CompositeCommand(
                    [
                        AddLineCommand(line_a[0], line_a[1], doc.active_layer),
                        AddLineCommand(line_b[0], line_b[1], doc.active_layer),
                    ]
                )
            )
            return ""
        self._viewer.start_tool(PipeToolSession())
        return ""

    def _cmd_move(self, args: List[str]) -> str:
        self._viewer.start_move_tool()
        return ""

    def _cmd_rotate(self, args: List[str]) -> str:
        self._viewer.start_rotate_tool()
        return ""

    def _cmd_scale(self, args: List[str]) -> str:
        self._viewer.start_scale_tool()
        return ""

    def _cmd_rotate_each(self, args: List[str]) -> str:
        self._viewer.start_rotate_each_tool()
        return ""

    def _cmd_scale_each(self, args: List[str]) -> str:
        self._viewer.start_scale_each_tool()
        return ""

    def _cmd_select_similar(self, args: List[str]) -> str:
        return self._viewer.select_similar()

    def _cmd_erase(self, args: List[str]) -> str:
        return self._viewer.delete_selected()

    def _cmd_undo(self, args: List[str]) -> str:
        return self._viewer.undo()

    def _cmd_redo(self, args: List[str]) -> str:
        return self._viewer.redo()

    @staticmethod
    def _parse_factor(token: str) -> float:
        try:
            factor = float(token.upper().rstrip("X"))
        except ValueError:
            raise _CommandError(f'Requires a numeric value: "{token}".') from None
        if factor <= 0:
            raise _CommandError("Scale factor must be positive.")
        return factor

    @staticmethod
    def _parse_point(token: str) -> Tuple[float, float]:
        x_str, _, y_str = token.partition(",")
        try:
            return float(x_str), float(y_str)
        except ValueError:
            raise _CommandError(f'Point must be given as "x,y": "{token}".') from None

    @classmethod
    def _parse_points(cls, tokens: List[str], count: int) -> List[Tuple[float, float]]:
        if len(tokens) < count:
            raise _CommandError("Point not specified.")
        return [cls._parse_point(t) for t in tokens[:count]]

