"""The Blocks palette: pick a ready-made block and place it on the sketch.

Two sources, as in AutoCAD's palette: the blocks the open drawing already defines (what
an imported sketch brings along - its GESUT symbols, say) and the library, which is the
app's own block files plus whatever DXF files the user adds with "+".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.blocks import LibraryBlock, add_to_library, library_blocks, read_block_file
from core.dxf_document import DXFDocument
from ui.dxf.block_render import Shape, block_shapes, file_shapes, shapes_pixmap
from ui.i18n import tr
from ui.theme import ICON_SM, SPACE_SM, SPACE_XS, Color
from ui.theme.icons import icon_manager
from ui.widgets import SegmentedControl, decimal_validator, make_button, make_field, styled_line_edit

_COLUMNS = 3
_TILE_ICON = 60
_PREVIEW_SIZE = 150
_TAB_DRAWING = "drawing"
_TAB_LIBRARY = "library"


@dataclass(frozen=True)
class BlockEntry:
    name: str
    # The library file it comes from, or None for a block the open drawing defines.
    source_path: Optional[str] = None


class _BlockTile(qw.QToolButton):

    doubleClicked = qc.pyqtSignal()

    def mouseDoubleClickEvent(self, event: qg.QMouseEvent) -> None:
        super().mouseDoubleClickEvent(event)
        self.doubleClicked.emit()


class BlockPanel(qw.QWidget):

    # The block, how it is drawn (its shapes, base point at the origin), rotation and scale.
    insertRequested = qc.pyqtSignal(object, object, float, float)

    def __init__(self, library_dirs: Sequence[str], user_dir: str, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("blockPanel")
        self._library_dirs = list(library_dirs)
        self._user_dir = user_dir
        self._doc: Optional[DXFDocument] = None
        self._drawing_names: Tuple[str, ...] = ()
        self._library: List[LibraryBlock] = []
        self._shapes: Dict[BlockEntry, List[Shape]] = {}
        self._selected: Optional[BlockEntry] = None
        self._tiles: List[_BlockTile] = []
        self._group = qw.QButtonGroup(self)
        self._group.setExclusive(True)

        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_SM)

        header = qw.QHBoxLayout()
        header.setSpacing(SPACE_XS)
        self._tabs = SegmentedControl(
            [(_TAB_LIBRARY, tr("block_panel.tab_library")), (_TAB_DRAWING, tr("block_panel.tab_drawing"))]
        )
        self._tabs.currentChanged.connect(lambda _key: self._rebuild_grid())
        header.addWidget(self._tabs, 1)
        add_btn = qw.QToolButton()
        add_btn.setObjectName("layerAddBtn")
        add_btn.setIcon(icon_manager.get("block_add", size=ICON_SM, color=Color.TEXT_MUTED))
        add_btn.setIconSize(qc.QSize(ICON_SM, ICON_SM))
        add_btn.setToolTip(tr("block_panel.add_tooltip"))
        add_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        header.addWidget(add_btn)
        layout.addLayout(header)

        self._search = styled_line_edit()
        self._search.setPlaceholderText(tr("block_panel.search"))
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(lambda _text: self._rebuild_grid())
        layout.addWidget(self._search)

        self._grid_host = qw.QWidget()
        self._grid = qw.QGridLayout(self._grid_host)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(SPACE_XS)
        # Equal columns even when a row is short, so one lone block is one tile wide.
        for column in range(_COLUMNS):
            self._grid.setColumnStretch(column, 1)
        layout.addWidget(self._grid_host)

        self._empty = qw.QLabel()
        self._empty.setObjectName("blockPanelEmpty")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty)

        layout.addSpacing(SPACE_SM)
        title = qw.QLabel(tr("block_panel.properties"))
        title.setObjectName("layerPanelTitle")
        layout.addWidget(title)

        self._preview = qw.QLabel()
        self._preview.setObjectName("blockPreview")
        self._preview.setAlignment(qc.Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumHeight(_PREVIEW_SIZE + 2 * SPACE_SM)
        layout.addWidget(self._preview)

        self._name = qw.QLabel()
        self._name.setObjectName("blockPanelName")
        layout.addWidget(self._name)

        fields = qw.QHBoxLayout()
        fields.setSpacing(SPACE_SM)
        self._rotation = styled_line_edit("0")
        self._rotation.setValidator(decimal_validator(-360.0, 360.0, 3))
        self._rotation.textChanged.connect(lambda _text: self._refresh_properties())
        fields.addWidget(make_field(tr("block_panel.rotation"), self._rotation))
        self._scale = styled_line_edit("1")
        self._scale.setValidator(decimal_validator(0.0001, 100000.0, 4))
        self._scale.setToolTip(tr("block_panel.scale_tooltip"))
        fields.addWidget(make_field(tr("block_panel.scale"), self._scale))
        layout.addLayout(fields)

        self._insert_btn = make_button(tr("block_panel.insert"), "primary", self._request_insert)
        layout.addWidget(self._insert_btn)
        layout.addStretch(1)

        self.refresh_library()

    # ---------- sources ----------

    def set_document(self, doc: Optional[DXFDocument]) -> None:
        names = tuple(doc.block_names()) if doc is not None else ()
        if doc is self._doc and names == self._drawing_names:
            return
        if doc is not self._doc:
            self._forget_shapes(from_library=False)
        self._doc = doc
        self._drawing_names = names
        self._rebuild_grid()

    def refresh_library(self) -> None:
        self._forget_shapes(from_library=True)
        self._library = library_blocks(self._library_dirs + [self._user_dir])
        self._rebuild_grid()

    def _forget_shapes(self, from_library: bool) -> None:
        self._shapes = {
            entry: shapes
            for entry, shapes in self._shapes.items()
            if (entry.source_path is not None) != from_library
        }

    def _entries(self) -> List[BlockEntry]:
        if self._tabs.current() == _TAB_DRAWING:
            return [BlockEntry(name) for name in self._drawing_names]
        return [BlockEntry(block.name, block.path) for block in self._library]

    def shapes_for(self, entry: BlockEntry) -> List[Shape]:
        cached = self._shapes.get(entry)
        if cached is not None:
            return cached
        try:
            if entry.source_path is not None:
                shapes = file_shapes(read_block_file(entry.source_path))
            elif self._doc is not None and self._doc.has_block(entry.name):
                shapes = block_shapes(self._doc.drawing, entry.name)
            else:
                shapes = []
        except Exception:
            # A file that no longer reads still gets a tile - just an empty one - rather
            # than taking the whole palette down with it.
            shapes = []
        self._shapes[entry] = shapes
        return shapes

    # ---------- grid ----------

    def _rebuild_grid(self) -> None:
        for tile in self._tiles:
            self._group.removeButton(tile)
            tile.hide()
            tile.deleteLater()
        self._tiles = []

        query = self._search.text().strip().casefold()
        entries = [entry for entry in self._entries() if query in entry.name.casefold()]
        for index, entry in enumerate(entries):
            tile = self._make_tile(entry)
            self._grid.addWidget(tile, index // _COLUMNS, index % _COLUMNS)
            self._tiles.append(tile)

        if entries:
            self._empty.hide()
        else:
            self._empty.setText(self._empty_text(query))
            self._empty.show()

        if self._selected not in entries:
            self._selected = None
        for tile in self._tiles:
            if tile.property("entry") == self._selected:
                tile.setChecked(True)
        self._refresh_properties()

    def _empty_text(self, query: str) -> str:
        if query:
            return tr("block_panel.no_match")
        if self._tabs.current() == _TAB_DRAWING:
            return tr("block_panel.drawing_empty")
        return tr("block_panel.library_empty")

    def _make_tile(self, entry: BlockEntry) -> _BlockTile:
        tile = _BlockTile()
        tile.setObjectName("blockTile")
        tile.setCheckable(True)
        tile.setToolButtonStyle(qc.Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        tile.setIconSize(qc.QSize(_TILE_ICON, _TILE_ICON))
        tile.setIcon(qg.QIcon(shapes_pixmap(self.shapes_for(entry), _TILE_ICON, qg.QColor(Color.TEXT))))
        tile.setText(self._elided(entry.name))
        tile.setToolTip(entry.name)
        tile.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        tile.setSizePolicy(qw.QSizePolicy.Policy.Expanding, qw.QSizePolicy.Policy.Fixed)
        tile.setProperty("entry", entry)
        tile.clicked.connect(lambda _checked=False, e=entry: self._select(e))
        tile.doubleClicked.connect(lambda e=entry: (self._select(e), self._request_insert()))
        self._group.addButton(tile)
        return tile

    def _elided(self, name: str) -> str:
        metrics = qg.QFontMetrics(self.font())
        return metrics.elidedText(name, qc.Qt.TextElideMode.ElideRight, _TILE_ICON + 20)

    def _select(self, entry: BlockEntry) -> None:
        self._selected = entry
        self._refresh_properties()

    # ---------- properties ----------

    def _rotation_value(self) -> float:
        try:
            return float(self._rotation.text())
        except ValueError:
            return 0.0

    def _scale_value(self) -> float:
        try:
            value = float(self._scale.text())
        except ValueError:
            return 1.0
        return value if value > 0 else 1.0

    def _refresh_properties(self) -> None:
        entry = self._selected
        self._insert_btn.setEnabled(entry is not None)
        if entry is None:
            self._preview.clear()
            self._preview.setText(tr("block_panel.pick_hint"))
            self._name.setText("")
            return
        pixmap = shapes_pixmap(
            self.shapes_for(entry), _PREVIEW_SIZE, qg.QColor(Color.TEXT), self._rotation_value()
        )
        self._preview.setPixmap(pixmap)
        self._name.setText(entry.name)

    def _request_insert(self) -> None:
        entry = self._selected
        if entry is None:
            return
        self.insertRequested.emit(entry, self.shapes_for(entry), self._rotation_value(), self._scale_value())

    # ---------- library ----------

    def _on_add_clicked(self) -> None:
        path, _filter = qw.QFileDialog.getOpenFileName(
            self, tr("block_panel.add_title"), "", tr("block_panel.add_filter")
        )
        if not path:
            return
        try:
            added = add_to_library(path, self._user_dir)
        except Exception as exc:
            qw.QMessageBox.warning(self, tr("block_panel.add_title"), tr("block_panel.add_failed", error=exc))
            return
        self._tabs.setCurrent(_TAB_LIBRARY)
        self._selected = BlockEntry(added.name, added.path)
        self.refresh_library()
