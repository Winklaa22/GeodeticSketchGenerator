from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

import ezdxf
from ezdxf import bbox as ezdxf_bbox
from ezdxf.addons.drawing import Frontend, RenderContext
from ezdxf.addons.drawing.config import Configuration

from core.commands.base import Command as EditCommand
from core.commands.composite import CompositeCommand
from core.commands.edit import DeleteEntityCommand, DuplicateEntitiesCommand, MoveCommand
from core.commands.history import CommandHistory
from core.commands.layers import (
    AddLayerCommand,
    DeleteLayerCommand,
    SetActiveLayerCommand,
    SetLayerColorCommand,
    SetLayerVisibleCommand,
    layers_to_prune,
)
from core.commands.text import (
    SetEntityColorCommand,
    SetTextContentCommand,
    SetTextHeightCommand,
    SetTextRotationCommand,
)
from core.dxf_document import DXFDocument
from core.plot import (
    ANNOTATION_TEXT_MM,
    PlotOptions,
    StrokeStyle,
    model_stroke_style,
    render_configuration,
    sheet_label,
    sheet_size_in_units,
    units_per_mm,
)
from core.table_template import ResolvedCell
from ui.dxf.backend import QtSceneBackend
from ui.dxf.command_line import CommandLine
from ui.dxf.compass import RotationCompass
from ui.dxf.graphics_view import CadGraphicsView
from ui.dxf.interpreter import DxfCommandInterpreter
from ui.dxf.items import HANDLE_ROLE
from ui.dxf.layer_panel import LayerPanel
from ui.dxf.page_frame import page_frame_for
from ui.dxf.pdf_export import PlotJob, export_sheets
from ui.dxf.sheet_tabs import SheetTabBar
from ui.dxf.text_options_bar import TextOptionsBar
from ui.dxf.toolbar import DxfToolbar
from ui.dxf.tools import (
    CircleToolSession,
    LineToolSession,
    MoveToolSession,
    PipeToolSession,
    PointToolSession,
    RotateEachToolSession,
    RotateToolSession,
    ScaleEachToolSession,
    ScaleToolSession,
    TextToolSession,
    ToolSession,
)
from ui.i18n import tr
from ui.theme import Color as UiColor, SPACE_MD, SPACE_SM, SPACE_XS
from ui.theme.icons import icon_manager


_TOOL_KEYS = {
    PointToolSession: "point",
    TextToolSession: "text",
    LineToolSession: "line",
    CircleToolSession: "circle",
    PipeToolSession: "pipe",
    MoveToolSession: "move",
    RotateToolSession: "rotate",
    ScaleToolSession: "scale",
    RotateEachToolSession: "rotate_each",
    ScaleEachToolSession: "scale_each",
}


class DxfViewer(qw.QWidget):

    documentChanged = qc.pyqtSignal()
    pageFrameMoved = qc.pyqtSignal(float, float)
    pageFrameRotated = qc.pyqtSignal(float)
    pageScaleZoomRequested = qc.pyqtSignal(float, float, float)

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._init_state()
        self._build_ui()
        self._wire_canvas()
        self._wire_toolbar()
        self._wire_layer_panel()
        self._register_shortcuts()
        self.ensure_document()

    def _init_state(self) -> None:
        self.entity_count = 0
        self.layer_count = 0
        self._doc: Optional[DXFDocument] = None
        self._history: Optional[CommandHistory] = None
        self._active_tool: Optional[ToolSession] = None
        self._selected_handles: List[str] = []
        self._clipboard_handles: List[str] = []
        self._clipboard_doc: Optional[DXFDocument] = None
        self._imported_layer_names: Optional[set] = None
        self._layout_options: Optional[PlotOptions] = None
        self._layout_center: Optional[Tuple[float, float]] = None
        self._layout_label = ""
        self._layout_rotation = 0.0
        self._layout_table_height_mm = 0.0
        self._layout_table_width_mm = 0.0

    def _build_ui(self) -> None:
        outer = qw.QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE_SM)

        canvas_column = qw.QWidget()
        layout = qw.QVBoxLayout(canvas_column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        self._toolbar = DxfToolbar()
        layout.addWidget(self._toolbar)

        self._stack = qw.QStackedWidget()
        layout.addWidget(self._stack)

        self._empty_page = self._build_empty_page()

        self._canvas_page = qw.QWidget()
        canvas_layout = qw.QVBoxLayout(self._canvas_page)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self._view = CadGraphicsView()
        self._text_options_bar = TextOptionsBar(self)
        self._command_line = CommandLine()
        self._sheet_tabs = SheetTabBar()
        self._compass = RotationCompass(self._canvas_page)
        canvas_layout.addWidget(self._view, 1)
        canvas_layout.addWidget(self._sheet_tabs)
        canvas_layout.addWidget(self._command_line)

        self._interpreter = DxfCommandInterpreter(self)

        self._stack.addWidget(self._empty_page)
        self._stack.addWidget(self._canvas_page)

        outer.addWidget(canvas_column, 1)
        self._layer_panel = LayerPanel()

    @staticmethod
    def _build_empty_page() -> qw.QWidget:
        page = qw.QWidget()
        page.setObjectName("dxfEmpty")
        layout = qw.QVBoxLayout(page)
        layout.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(SPACE_SM)
        icon = qw.QLabel()
        icon.setObjectName("dxfEmptyIcon")
        icon.setPixmap(icon_manager.get("dxf_icon", size=24, color=UiColor.TEXT_FAINT).pixmap(24, 24))
        icon.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        text = qw.QLabel(tr("viewer.empty_hint"))
        text.setObjectName("dxfEmptyText")
        text.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)
        layout.addWidget(text)
        return page

    def _wire_canvas(self) -> None:
        self._view.entitySelected.connect(self._on_entity_selected)
        self._view.toolPointPlaced.connect(self._on_tool_point_placed)
        self._view.itemsDragMoved.connect(self._on_items_drag_moved)
        self._view.viewportChanged.connect(self._reposition_text_options_bar)
        self._view.pageFrameMoved.connect(self._on_page_frame_moved)
        self._view.pageScaleZoomRequested.connect(self.pageScaleZoomRequested)
        self._view.viewportChanged.connect(self._reposition_compass)

        self._compass.rotationChanged.connect(self._on_compass_rotation_changed)
        self._compass.rotationCommitted.connect(self._on_compass_rotation_committed)
        self._compass.resetRequested.connect(self._on_compass_reset)

        self._text_options_bar.contentChanged.connect(self._on_text_content_changed)
        self._text_options_bar.heightChanged.connect(self._on_text_height_changed)
        self._text_options_bar.rotationChanged.connect(self._on_text_rotation_changed)
        self._text_options_bar.colorChanged.connect(self._on_text_color_changed)

        self._command_line.commandEntered.connect(self._on_command_entered)
        self._command_line.undoRequested.connect(lambda: self._echo(self.undo()))
        self._command_line.redoRequested.connect(lambda: self._echo(self.redo()))

    def _wire_toolbar(self) -> None:
        self._toolbar.pointRequested.connect(lambda: self._start_draw_tool(PointToolSession))
        self._toolbar.textRequested.connect(lambda: self._start_draw_tool(self._text_tool))
        self._toolbar.lineRequested.connect(lambda: self._start_draw_tool(LineToolSession))
        self._toolbar.circleRequested.connect(lambda: self._start_draw_tool(CircleToolSession))
        self._toolbar.pipeRequested.connect(lambda: self._start_draw_tool(PipeToolSession))
        self._toolbar.selectRequested.connect(self.cancel_tool)
        self._toolbar.moveRequested.connect(self.start_move_tool)
        self._toolbar.rotateRequested.connect(self.start_rotate_tool)
        self._toolbar.scaleRequested.connect(self.start_scale_tool)
        self._toolbar.rotateEachRequested.connect(self.start_rotate_each_tool)
        self._toolbar.scaleEachRequested.connect(self.start_scale_each_tool)
        self._toolbar.selectSimilarRequested.connect(lambda: self._echo(self.select_similar()))
        self._toolbar.eraseRequested.connect(lambda: self._echo(self.delete_selected()))
        self._toolbar.zoomExtentsRequested.connect(self._view.fit_to_page)
        self._toolbar.zoomInRequested.connect(lambda: self._view.zoom_by(1.25))
        self._toolbar.zoomOutRequested.connect(lambda: self._view.zoom_by(0.8))

    def _wire_layer_panel(self) -> None:
        self._layer_panel.addLayerRequested.connect(self._on_add_layer)
        self._layer_panel.deleteLayerRequested.connect(lambda n: self.execute_command(DeleteLayerCommand(n)))
        self._layer_panel.colorChangeRequested.connect(
            lambda n, rgb: self.execute_command(SetLayerColorCommand(n, rgb))
        )
        self._layer_panel.visibilityToggled.connect(
            lambda n, v: self.execute_command(SetLayerVisibleCommand(n, v))
        )
        self._layer_panel.setActiveRequested.connect(
            lambda n: self.execute_command(SetActiveLayerCommand(n))
        )
        self._layer_panel.selectLayerRequested.connect(self.select_by_layer)
        self._layer_panel.pruneLayersRequested.connect(self._on_prune_layers)

    def _register_shortcuts(self) -> None:
        self._add_shortcut(
            "Ctrl+Z", lambda: self._echo(self.undo()), context=qc.Qt.ShortcutContext.WindowShortcut
        )
        self._add_shortcut(
            "Ctrl+Y", lambda: self._echo(self.redo()), context=qc.Qt.ShortcutContext.WindowShortcut
        )
        self._add_shortcut("Delete", lambda: self._echo(self.delete_selected()))
        self._add_shortcut("Esc", self.cancel_tool)
        self._add_shortcut("Ctrl+C", lambda: self._echo(self.copy_selected()))
        self._add_shortcut("Ctrl+V", lambda: self._echo(self.paste_clipboard()))
        self._add_shortcut("Ctrl+D", lambda: self._echo(self.duplicate_selected()))

        self._add_shortcut("P,O", lambda: self._start_draw_tool(PointToolSession), parent=self._view)
        self._add_shortcut("T", lambda: self._start_draw_tool(self._text_tool), parent=self._view)
        self._add_shortcut("L", lambda: self._start_draw_tool(LineToolSession), parent=self._view)
        self._add_shortcut("C", lambda: self._start_draw_tool(CircleToolSession), parent=self._view)
        self._add_shortcut("R,U", lambda: self._start_draw_tool(PipeToolSession), parent=self._view)
        self._add_shortcut("M", self.start_move_tool, parent=self._view)
        self._add_shortcut("R,O", self.start_rotate_tool, parent=self._view)
        self._add_shortcut("S,C", self.start_scale_tool, parent=self._view)
        self._add_shortcut("R,E", self.start_rotate_each_tool, parent=self._view)
        self._add_shortcut("S,E", self.start_scale_each_tool, parent=self._view)
        self._add_shortcut("S,S", lambda: self._echo(self.select_similar()), parent=self._view)

    def _add_shortcut(
        self,
        sequence: str,
        slot,
        context: qc.Qt.ShortcutContext = qc.Qt.ShortcutContext.WidgetWithChildrenShortcut,
        parent: Optional[qw.QWidget] = None,
    ) -> None:
        shortcut = qg.QShortcut(qg.QKeySequence(sequence), parent or self)
        shortcut.setContext(context)
        shortcut.activated.connect(slot)

    @property
    def view(self) -> CadGraphicsView:
        return self._view

    @property
    def has_document(self) -> bool:
        return self._doc is not None

    @property
    def layer_panel(self) -> LayerPanel:
        return self._layer_panel

    @property
    def sheet_tabs(self) -> SheetTabBar:
        return self._sheet_tabs

    def _text_tool(self) -> TextToolSession:
        if self._layout_options is None:
            return TextToolSession()
        return TextToolSession(ANNOTATION_TEXT_MM * units_per_mm(self._layout_options))

    @property
    def layout_options(self) -> Optional[PlotOptions]:
        return self._layout_options

    def set_layout_mode(
        self,
        options: Optional[PlotOptions],
        center: Optional[Tuple[float, float]] = None,
        label: str = "",
        rotation: float = 0.0,
        table_height_mm: float = 0.0,
        table_width_mm: float = 0.0,
        preserve_view: bool = False,
    ) -> None:
        if options is None:
            if self._layout_options is None:
                return
            self._layout_options = None
            self._layout_center = None
            self._layout_label = ""
            self._layout_rotation = 0.0
            self._layout_table_height_mm = 0.0
            self._layout_table_width_mm = 0.0
            self._view.set_page_frame(None)
            self._view.set_title_block([])
            self._compass.set_angle(0.0)
        else:
            new_center = center or self._layout_center or self.content_center() or (0.0, 0.0)
            # A preserved zoom/pan only stays meaningful if the sheet's physical
            # footprint - both its size and where it's centered - hasn't
            # changed. Paper size/scale changing is one way that breaks; a
            # sheet with no manually dragged center (the common case) also
            # re-centers on the document's content bbox on every render, so
            # restoring an old view once that centroid has moved (e.g. after
            # "Apply to DXF" adds more entities) would leave the preview
            # looking at a stale location that no longer matches the frame -
            # or what actually gets exported, which always resolves the
            # center fresh - so fall back to a fresh fit-to-page whenever
            # either part of that footprint is different.
            if preserve_view and self._layout_options is not None:
                preserve_view = (
                    sheet_size_in_units(self._layout_options) == sheet_size_in_units(options)
                    and self._layout_center == new_center
                )
            self._view.reset_view_rotation()
            self._layout_options = options
            self._layout_center = new_center
            self._layout_label = label or sheet_label(options)
            self._layout_rotation = rotation
            self._layout_table_height_mm = table_height_mm
            self._layout_table_width_mm = table_width_mm
            self._install_page_frame()
            self._compass.set_angle(rotation)
        if self._doc is not None:
            self._render(preserve_view=preserve_view)

    def move_page_frame(self, center_x: float, center_y: float) -> None:
        if self._layout_options is None:
            return
        self._layout_center = (center_x, center_y)
        self._install_page_frame()

    def _install_page_frame(self) -> None:
        assert self._layout_options is not None and self._layout_center is not None
        self._view.set_page_frame(
            page_frame_for(
                self._layout_options, self._layout_center, self._layout_label, self._layout_rotation,
                table_height_mm=self._layout_table_height_mm, table_width_mm=self._layout_table_width_mm,
            )
        )

    def set_title_block(self, cells: List[ResolvedCell], scale: float = 1.0) -> None:
        self._view.set_title_block(cells, scale)

    def _on_page_frame_moved(self, center_x: float, center_y: float) -> None:
        self.move_page_frame(center_x, center_y)
        self.pageFrameMoved.emit(center_x, center_y)

    def current_zoom_factor(self) -> float:
        return self._view.current_zoom_factor()

    def apply_zoom_factor(self, factor: float) -> None:
        self._view.apply_zoom_factor(factor)

    def _reposition_compass(self) -> None:
        viewport = self._view.viewport()
        top_right = viewport.mapToGlobal(qc.QPoint(viewport.width(), 0))
        anchor = self._canvas_page.mapFromGlobal(top_right)
        self._compass.move(anchor.x() - self._compass.width() - SPACE_MD, anchor.y() + SPACE_MD)
        self._compass.raise_()

    def _on_compass_rotation_changed(self, angle: float) -> None:
        if self._layout_options is not None:
            self._view.rotate_page_frame_live(angle)
        else:
            self._view.set_view_rotation(angle)

    def _on_compass_rotation_committed(self, angle: float) -> None:
        if self._layout_options is not None:
            self._layout_rotation = self._view.page_frame_rotation()
            self.pageFrameRotated.emit(self._layout_rotation)

    def _on_compass_reset(self) -> None:
        self._compass.set_angle(0.0)
        if self._layout_options is not None:
            self._view.rotate_page_frame_live(0.0)
            self._layout_rotation = 0.0
            self.pageFrameRotated.emit(0.0)
        else:
            self._view.reset_view_rotation()

    def _on_page_frame_rotated(self, rotation: float) -> None:
        self._layout_rotation = rotation
        self.pageFrameRotated.emit(rotation)

    def _render_config(self) -> Configuration:
        if self._layout_options is None:
            return Configuration()
        return render_configuration(self._layout_options)

    def _stroke_style(self) -> Optional[StrokeStyle]:
        if self._layout_options is None:
            return None
        return model_stroke_style(self._layout_options)

    def content_bbox(self):
        if self._doc is None:
            return None
        box = ezdxf_bbox.extents(self._doc.modelspace)
        return box if box.has_data else None

    def content_center(self) -> Optional[Tuple[float, float]]:
        box = self.content_bbox()
        return (box.center.x, box.center.y) if box is not None else None

    def export_sheets(
        self, file_path: str, jobs: Sequence[PlotJob], title: str = ""
    ) -> Tuple[bool, str]:
        if self._doc is None:
            return False, tr("viewer.no_drawing_to_export")
        return export_sheets(self._doc, file_path, jobs, title)

    def save_document(self, file_path: str) -> None:
        assert self._doc is not None
        self._doc.save(file_path)

    def ensure_document(self) -> DXFDocument:
        if self._doc is None:
            self._doc = DXFDocument.new()
            self._history = CommandHistory()
            self._selected_handles = []
            self._render(preserve_view=False)
            self._command_line.reset()
            self._stack.setCurrentWidget(self._canvas_page)
        return self._doc

    def show_empty(self) -> None:
        self._stack.setCurrentWidget(self._empty_page)

    def clear(self) -> None:
        self.cancel_tool()
        self._view.scene().clear()
        self._view.set_selected_items([])
        self.entity_count = 0
        self.layer_count = 0
        self._doc = None
        self._view.set_document(None)
        self._history = None
        self._selected_handles = []
        self._imported_layer_names = None
        self._layer_panel.refresh([])
        self._layer_panel.set_prune_available(False)
        self.show_empty()

    def load_file(self, file_path: str) -> Tuple[bool, str]:
        try:
            doc = DXFDocument.load(file_path)
        except IOError as exc:
            return False, tr("viewer.could_not_read_file", error=exc)
        except ezdxf.DXFError as exc:
            return False, tr("viewer.not_valid_dxf", error=exc)
        return self._adopt_document(doc)

    def load_from_text(self, content: str) -> Tuple[bool, str]:
        try:
            doc = DXFDocument.from_text(content)
        except ezdxf.DXFError as exc:
            return False, tr("viewer.could_not_restore_snapshot", error=exc)
        return self._adopt_document(doc)

    def to_dxf_text(self) -> Optional[str]:
        if self._doc is None:
            return None
        return self._doc.to_text()

    def _adopt_document(self, doc: DXFDocument) -> Tuple[bool, str]:
        self._doc = doc
        self._history = CommandHistory()
        self._selected_handles = []
        self._imported_layer_names = {info.name for info in doc.iter_layers()}
        try:
            self._render(preserve_view=False)
        except Exception as exc:
            self._doc = None
            self._view.set_document(None)
            self._history = None
            self._imported_layer_names = None
            return False, tr("viewer.could_not_render", error=exc)

        self._command_line.reset()
        self._stack.setCurrentWidget(self._canvas_page)
        return True, ""

    def execute_command(self, command: EditCommand) -> None:
        self.ensure_document()
        assert self._doc is not None and self._history is not None
        self._history.execute(command, self._doc)
        self._render(preserve_view=True)

    def undo(self) -> str:
        if self._doc is None or self._history is None or not self._history.undo(self._doc):
            return tr("viewer.nothing_to_undo")
        self.clear_selection()
        self._render(preserve_view=True)
        return ""

    def redo(self) -> str:
        if self._doc is None or self._history is None or not self._history.redo(self._doc):
            return tr("viewer.nothing_to_redo")
        self.clear_selection()
        self._render(preserve_view=True)
        return ""

    def delete_selected(self) -> str:
        if not self._selected_handles:
            return tr("common.select_object_first")
        self.execute_command(DeleteEntityCommand(self._selected_handles))
        self.clear_selection()
        return ""

    def clear_selection(self) -> None:
        self._selected_handles = []
        self._view.set_selected_items([])
        self._toolbar.set_erase_enabled(False)
        self._sync_text_options_bar()

    def select_by_layer(self, name: str) -> None:
        if self._doc is None:
            return
        handles = {entity.dxf.handle for entity in self._doc.modelspace if entity.dxf.layer == name}
        self._select_handles(handles)

    def _select_handles(self, handles: Iterable[str]) -> None:
        handle_set = set(handles)
        items = [item for item in self._view.scene().items() if item.data(HANDLE_ROLE) in handle_set]
        self._view.set_selected_items(items)
        self._selected_handles = [item.data(HANDLE_ROLE) for item in items]
        self._toolbar.set_erase_enabled(bool(items))
        self._sync_text_options_bar()

    def start_tool(self, tool: ToolSession) -> None:
        self.cancel_tool()
        self.clear_selection()
        self._active_tool = tool
        self._view.set_tool(tool)
        self._command_line.show_response(tool.prompt)
        self._command_line.focus_input()
        self._toolbar.set_active_tool(_TOOL_KEYS.get(type(tool)))

    def cancel_tool(self) -> None:
        if self._active_tool is not None:
            self._active_tool.cleanup(self._view.scene())
            self._active_tool = None
            self._view.set_tool(None)
            self._command_line.show_response(tr("viewer.cancelled"))
        self.clear_selection()
        self._toolbar.set_active_tool(None)
        self._view.setFocus()

    def _start_draw_tool(self, factory: Callable[[], ToolSession]) -> None:
        self.ensure_document()
        self.start_tool(factory())

    def start_move_tool(self) -> None:
        if not self._selected_handles:
            self._echo(tr("viewer.select_to_move"))
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(MoveToolSession(list(self._selected_handles)))

    def start_rotate_tool(self) -> None:
        if not self._selected_handles:
            self._echo(tr("viewer.select_to_rotate"))
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(RotateToolSession(list(self._selected_handles)))

    def start_scale_tool(self) -> None:
        if not self._selected_handles:
            self._echo(tr("viewer.select_to_scale"))
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(ScaleToolSession(list(self._selected_handles)))

    def start_rotate_each_tool(self) -> None:
        if not self._selected_handles:
            self._echo(tr("viewer.select_to_rotate"))
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(RotateEachToolSession(list(self._selected_handles)))

    def start_scale_each_tool(self) -> None:
        if not self._selected_handles:
            self._echo(tr("viewer.select_to_scale"))
            self._toolbar.set_active_tool(None)
            return
        self.start_tool(ScaleEachToolSession(list(self._selected_handles)))

    def copy_selected(self) -> str:
        if not self._selected_handles:
            return tr("common.select_object_first")
        self._clipboard_doc = self._doc
        self._clipboard_handles = list(self._selected_handles)
        return tr("viewer.objects_copied", count=len(self._clipboard_handles))

    def paste_clipboard(self) -> str:
        if self._clipboard_doc is not self._doc or not self._clipboard_handles:
            return tr("viewer.nothing_to_paste")
        dx, dy = self._view.default_duplicate_offset()
        command = DuplicateEntitiesCommand(self._clipboard_handles, dx, dy)
        self.execute_command(command)
        self._select_handles(command.new_handles)
        return tr("viewer.objects_pasted", count=len(command.new_handles))

    def duplicate_selected(self) -> str:
        if not self._selected_handles:
            return tr("common.select_object_first")
        dx, dy = self._view.default_duplicate_offset()
        command = DuplicateEntitiesCommand(self._selected_handles, dx, dy)
        self.execute_command(command)
        self._select_handles(command.new_handles)
        return tr("viewer.objects_duplicated", count=len(command.new_handles))

    def select_similar(self) -> str:
        if self._doc is None or not self._selected_handles:
            return tr("common.select_object_first")
        matched = set()
        for handle in self._selected_handles:
            matched.update(self._doc.find_similar(handle))
        self._select_handles(matched)
        return tr("viewer.objects_selected", count=len(matched))

    def _on_add_layer(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self.ensure_document()
        self.execute_command(AddLayerCommand(name, rgb))

    def _on_prune_layers(self) -> None:
        if self._doc is None or self._imported_layer_names is None:
            return
        existing_names = {info.name for info in self._doc.iter_layers()}
        to_delete = layers_to_prune(self._imported_layer_names, existing_names)
        if not to_delete:
            self._echo(tr("viewer.no_layers_to_remove"))
            return
        preview = ", ".join(to_delete[:8]) + (
            tr("viewer.more_suffix", count=len(to_delete) - 8) if len(to_delete) > 8 else ""
        )
        confirmed = qw.QMessageBox.question(
            self,
            tr("viewer.remove_layers_title"),
            tr("viewer.remove_layers_message", count=len(to_delete), preview=preview),
            qw.QMessageBox.StandardButton.Yes | qw.QMessageBox.StandardButton.No,
            qw.QMessageBox.StandardButton.No,
        )
        if confirmed != qw.QMessageBox.StandardButton.Yes:
            return
        self.execute_command(CompositeCommand([DeleteLayerCommand(name) for name in to_delete]))
        self._echo(tr("viewer.removed_layers", count=len(to_delete)))

    def _on_command_entered(self, text: str) -> None:
        if self._active_tool is not None:
            message = self._active_tool.on_text(text)
            if message:
                self._command_line.show_response(message)
            elif self._active_tool.is_done():
                self._finish_tool()
            else:
                self._command_line.show_response(self._active_tool.prompt)
            return
        response = self._interpreter.run(text)
        self._command_line.show_response(response)

    def _on_tool_point_placed(self) -> None:
        if self._active_tool is None:
            return
        if self._active_tool.is_done():
            self._finish_tool()
        else:
            self._command_line.show_response(self._active_tool.prompt)
            self._command_line.focus_input()

    def _on_entity_selected(self, handles: List[str]) -> None:
        self._selected_handles = list(handles)
        self._toolbar.set_erase_enabled(bool(handles))
        self._sync_text_options_bar()

    def _on_items_drag_moved(self, handles: List[str], dx: float, dy: float) -> None:
        self._selected_handles = list(handles)
        self.execute_command(MoveCommand(handles, dx, dy))

    def _sync_text_options_bar(self) -> None:
        if self._doc is None or len(self._selected_handles) != 1:
            self._text_options_bar.hide()
            return
        handle = self._selected_handles[0]
        entity = self._doc.get_entity(handle)
        if entity is None or entity.dxftype() != "TEXT":
            self._text_options_bar.hide()
            return
        self._text_options_bar.bind(
            handle, entity.dxf.text, entity.dxf.height, entity.dxf.rotation, self._doc.get_entity_color(handle)
        )
        self._reposition_text_options_bar()

    def _reposition_text_options_bar(self) -> None:
        bar = self._text_options_bar
        if not bar.isVisible() or bar.handle is None:
            return
        item = self._find_item(bar.handle)
        if item is None:
            bar.hide()
            return
        rect = item.sceneBoundingRect()
        corners = [
            self._view.mapFromScene(rect.topLeft()),
            self._view.mapFromScene(rect.topRight()),
            self._view.mapFromScene(rect.bottomLeft()),
            self._view.mapFromScene(rect.bottomRight()),
        ]
        center_x = sum(p.x() for p in corners) / len(corners)
        top_y = min(p.y() for p in corners)
        global_point = self._view.viewport().mapToGlobal(qc.QPoint(round(center_x), round(top_y)))
        anchor = self.mapFromGlobal(global_point)
        bar.move(anchor.x() - bar.width() // 2, anchor.y() - bar.height() - SPACE_SM)
        bar.raise_()

    def _find_item(self, handle: str) -> Optional[qw.QGraphicsItem]:
        for item in self._view.scene().items():
            if item.data(HANDLE_ROLE) == handle:
                return item
        return None

    def _on_text_content_changed(self, handle: str, text: str) -> None:
        self.execute_command(SetTextContentCommand(handle, text))

    def _on_text_height_changed(self, handle: str, height: float) -> None:
        self.execute_command(SetTextHeightCommand(handle, height))

    def _on_text_rotation_changed(self, handle: str, rotation: float) -> None:
        self.execute_command(SetTextRotationCommand(handle, rotation))

    def _on_text_color_changed(self, handle: str, rgb: Tuple[int, int, int]) -> None:
        self.execute_command(SetEntityColorCommand(handle, rgb))

    def _finish_tool(self) -> None:
        tool = self._active_tool
        assert tool is not None
        doc = self.ensure_document()
        command = tool.build_command(doc)
        next_tool = tool.continuation() if hasattr(tool, "continuation") else None
        tool.cleanup(self._view.scene())
        self._active_tool = None
        self._view.set_tool(None)
        self._toolbar.set_active_tool(None)
        self.execute_command(command)
        if next_tool is not None:
            self.start_tool(next_tool)
            return
        handle = getattr(command, "handle", None)
        if handle is not None:
            self._select_handles([handle])
        self._view.setFocus()

    def _echo(self, message: str) -> None:
        self._command_line.show_response(message)

    def echo(self, message: str) -> None:
        self._echo(message)

    def can_undo(self) -> bool:
        return self._history is not None and self._history.can_undo()

    def can_redo(self) -> bool:
        return self._history is not None and self._history.can_redo()

    def _render(self, *, preserve_view: bool) -> None:
        assert self._doc is not None
        self._view.set_document(self._doc)
        saved = self._view.save_view() if preserve_view else None
        scene = qw.QGraphicsScene()
        backend = QtSceneBackend(scene, self._stroke_style())
        context = RenderContext(self._doc.drawing)
        Frontend(context, backend, config=self._render_config()).draw_layout(
            self._doc.modelspace, finalize=True
        )
        self._view.setScene(scene)
        if self._layout_options is not None:
            self._view.set_content_rotation(self._layout_rotation, self._layout_center)
        if saved is not None:
            self._view.restore_view(saved)
        else:
            self._view.fit_to_page()

        handle_set = set(self._selected_handles)
        matched = [item for item in scene.items() if item.data(HANDLE_ROLE) in handle_set]
        self._view.set_selected_items(matched)
        self._selected_handles = [item.data(HANDLE_ROLE) for item in matched]
        self._toolbar.set_erase_enabled(bool(self._selected_handles))
        self.entity_count = self._doc.entity_count()
        self.layer_count = self._doc.layer_count()
        self._layer_panel.refresh(self._doc.iter_layers())
        self._layer_panel.set_prune_available(self._imported_layer_names is not None)
        self._sync_text_options_bar()
        self.documentChanged.emit()
