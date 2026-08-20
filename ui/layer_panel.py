"""Layers panel — docked to the right of the DXF canvas (see DxfViewer): one
row per layer with active/select/color/visibility/delete controls, plus an
"Add layer" affordance at the bottom.

Pure UI: every row action is a signal carrying plain values (str, bool,
tuple), never a Command or an ezdxf object — DxfViewer turns each one into
the matching `core.commands.layers` Command and executes it, same pattern
already used for DxfToolbar.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6 import QtCore as qc, QtGui as qg, QtWidgets as qw

from core.dxf_document import LayerInfo
from ui.theme import SPACE_XS

# Budget left for the name label once the active/swatch/visibility/delete
# icon-buttons and margins/spacing take their share of the row — long names
# (common in real-world layer naming, e.g. Polish cadastral exports) get
# elided rather than forcing the whole panel to scroll horizontally.
_NAME_MAX_WIDTH = 220

# Cycled through for a new layer's default color, in the order layers are added.
_AUTO_PALETTE: List[Tuple[int, int, int]] = [
    (145, 132, 217),  # accent purple
    (127, 207, 158),  # green
    (229, 130, 138),  # red
    (232, 181, 104),  # amber
    (110, 180, 219),  # blue
    (216, 143, 209),  # pink
    (163, 201, 105),  # lime
    (219, 158, 94),  # orange
]


def _next_color(existing_count: int) -> Tuple[int, int, int]:
    return _AUTO_PALETTE[existing_count % len(_AUTO_PALETTE)]


class _LayerRow(qw.QFrame):
    """One layer's controls: active indicator, name (+ entity count), color
    swatch, visibility checkbox, delete button."""

    activateRequested = qc.pyqtSignal(str)
    selectRequested = qc.pyqtSignal(str)
    colorRequested = qc.pyqtSignal(str, tuple)
    visibilityToggled = qc.pyqtSignal(str, bool)
    deleteRequested = qc.pyqtSignal(str)

    def __init__(self, info: LayerInfo, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self._name = info.name
        self.setObjectName("layerRow")
        self.setProperty("active", "true" if info.is_active else "false")

        layout = qw.QHBoxLayout(self)
        layout.setContentsMargins(SPACE_XS, SPACE_XS, SPACE_XS, SPACE_XS)
        layout.setSpacing(SPACE_XS)

        active_btn = qw.QToolButton()
        active_btn.setObjectName("layerActiveBtn")
        active_btn.setText("●" if info.is_active else "○")
        active_btn.setToolTip("Set as active layer — new entities draw here")
        active_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        active_btn.clicked.connect(lambda: self.activateRequested.emit(self._name))
        layout.addWidget(active_btn)

        name_btn = qw.QToolButton()
        name_btn.setObjectName("layerNameBtn")
        label = info.name if info.entity_count == 0 else f"{info.name} ({info.entity_count})"
        elided = qg.QFontMetrics(name_btn.font()).elidedText(
            label, qc.Qt.TextElideMode.ElideRight, _NAME_MAX_WIDTH
        )
        name_btn.setText(elided)
        name_btn.setToolTip(f'{label} — click to select all entities on this layer')
        name_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        name_btn.clicked.connect(lambda: self.selectRequested.emit(self._name))
        layout.addWidget(name_btn, 1)

        swatch = qw.QToolButton()
        swatch.setObjectName("layerColorSwatch")
        swatch.setToolTip("Change color")
        swatch.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        swatch.setStyleSheet(f"background-color: rgb{info.rgb};")
        swatch.clicked.connect(lambda: self._pick_color(info.rgb))
        layout.addWidget(swatch)

        visible_box = qw.QCheckBox()
        visible_box.setObjectName("layerVisibleCheck")
        visible_box.setToolTip("Show/hide this layer")
        visible_box.setChecked(info.visible)
        visible_box.toggled.connect(lambda checked: self.visibilityToggled.emit(self._name, checked))
        layout.addWidget(visible_box)

        delete_btn = qw.QToolButton()
        delete_btn.setObjectName("layerDeleteBtn")
        delete_btn.setText("✕")
        delete_btn.setToolTip("Delete layer" if info.name != "0" else 'Layer "0" cannot be deleted')
        delete_btn.setEnabled(info.name != "0")
        delete_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(self._name))
        layout.addWidget(delete_btn)

    def _pick_color(self, current_rgb: Tuple[int, int, int]) -> None:
        initial = qg.QColor(*current_rgb)
        color = qw.QColorDialog.getColor(initial, self, "Layer Color")
        if color.isValid():
            self.colorRequested.emit(self._name, (color.red(), color.green(), color.blue()))


class LayerPanel(qw.QWidget):
    """Slim vertical list of layer rows. `refresh()` rebuilds it from a
    fresh `DXFDocument.iter_layers()` snapshot every time the document
    changes — cheap enough (a handful of rows) not to need incremental
    diffing, same "full rebuild" approach the canvas render already uses."""

    addLayerRequested = qc.pyqtSignal(str, tuple)
    deleteLayerRequested = qc.pyqtSignal(str)
    colorChangeRequested = qc.pyqtSignal(str, tuple)
    visibilityToggled = qc.pyqtSignal(str, bool)
    setActiveRequested = qc.pyqtSignal(str)
    selectLayerRequested = qc.pyqtSignal(str)
    pruneLayersRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("layerPanel")

        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XS)

        title = qw.QLabel("Layers")
        title.setObjectName("layerPanelTitle")
        layout.addWidget(title)

        self._rows_container = qw.QWidget()
        self._rows_container.setObjectName("layerRowsContainer")
        self._rows_layout = qw.QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)

        scroll = qw.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(qw.QFrame.Shape.NoFrame)
        scroll.setWidget(self._rows_container)
        layout.addWidget(scroll, 1)

        bottom_row = qw.QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(SPACE_XS)

        add_btn = qw.QToolButton()
        add_btn.setObjectName("layerAddBtn")
        add_btn.setText("+ Add layer")
        add_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        bottom_row.addWidget(add_btn, 1)

        self._prune_btn = qw.QToolButton()
        self._prune_btn.setObjectName("layerPruneBtn")
        self._prune_btn.setText("🧹")
        self._prune_btn.setCursor(qc.Qt.CursorShape.PointingHandCursor)
        self._prune_btn.clicked.connect(self._on_prune_clicked)
        self._prune_btn.setEnabled(False)
        self._set_prune_tooltip(available=False)
        bottom_row.addWidget(self._prune_btn)

        layout.addLayout(bottom_row)

        self._layer_count = 0

    def refresh(self, layers: List[LayerInfo]) -> None:
        # Orphan old rows immediately (setParent(None)) rather than
        # deleteLater(): refresh() can run several times back-to-back within
        # one Python call (e.g. a composite command), with no event-loop
        # turn in between to process a deferred deletion — deleteLater()
        # left stale rows around long enough in that case to crash.
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        self._layer_count = len(layers)
        for info in layers:
            row = _LayerRow(info, self._rows_container)
            row.activateRequested.connect(self.setActiveRequested.emit)
            row.selectRequested.connect(self.selectLayerRequested.emit)
            row.colorRequested.connect(self.colorChangeRequested.emit)
            row.visibilityToggled.connect(self.visibilityToggled.emit)
            row.deleteRequested.connect(self.deleteLayerRequested.emit)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)

    def _on_add_clicked(self) -> None:
        name, ok = qw.QInputDialog.getText(self, "New Layer", "Layer name:")
        name = name.strip()
        if not ok or not name:
            return
        self.addLayerRequested.emit(name, _next_color(self._layer_count))

    def _on_prune_clicked(self) -> None:
        self.pruneLayersRequested.emit()

    def set_prune_available(self, available: bool) -> None:
        """Enabled only once a DXF has actually been imported — there's no
        "imported layers" snapshot to prune against in a blank drawing."""
        self._prune_btn.setEnabled(available)
        self._set_prune_tooltip(available)

    def _set_prune_tooltip(self, available: bool) -> None:
        if available:
            text = (
                "Remove imported layers not starting with 994, 211, or 219\n"
                "(layers added since importing are never touched)"
            )
        else:
            text = "Import a DXF file to use this"
        self._prune_btn.setToolTip(text)
