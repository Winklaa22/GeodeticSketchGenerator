from __future__ import annotations

import json
from typing import List, Optional, Tuple

from PyQt6.QtCore import QSettings, QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QInputDialog, QToolButton, QVBoxLayout, QWidget

from ui.icons import icon_manager
from ui.theme import Color, ICON_SM, SPACE_XS
from ui.widgets import ColorSwatchButton, SectionColumn

DEFAULT_LAYER_NAME = "0"
DEFAULT_LAYER_RGB: Tuple[int, int, int] = (145, 132, 217)
SETTINGS_KEY = "layers_v2"

_AUTO_PALETTE: List[Tuple[int, int, int]] = [
    (145, 132, 217),  # accent purple
    (127, 207, 158),  # green
    (229, 130, 138),  # red
    (232, 181, 104),  # amber
    (110, 180, 219),  # blue
    (216, 143, 209),  # pink
]


class _LayerDefRow(QFrame):

    defaultRequested = pyqtSignal(str)
    colorRequested = pyqtSignal(str, tuple)
    deleteRequested = pyqtSignal(str)

    def __init__(self, name: str, rgb: Tuple[int, int, int], is_default: bool, deletable: bool) -> None:
        super().__init__()
        self.setObjectName("layerRow")
        self.setProperty("active", "true" if is_default else "false")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_XS, SPACE_XS, SPACE_XS, SPACE_XS)
        layout.setSpacing(SPACE_XS)

        default_btn = QToolButton()
        default_btn.setObjectName("layerActiveBtn")
        active_icon = "layer_active" if is_default else "layer_inactive"
        default_btn.setIcon(icon_manager.get(active_icon, size=ICON_SM, color=Color.ACCENT))
        default_btn.setIconSize(QSize(ICON_SM, ICON_SM))
        default_btn.setToolTip("Set as default — used by modes with no layer picker of their own")
        default_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        default_btn.clicked.connect(lambda: self.defaultRequested.emit(name))
        layout.addWidget(default_btn)

        label = QToolButton()
        label.setObjectName("layerNameBtn")
        label.setText(name)
        layout.addWidget(label, 1)

        swatch = ColorSwatchButton(rgb, "Change color")
        swatch.colorChanged.connect(lambda new_rgb: self.colorRequested.emit(name, new_rgb))
        layout.addWidget(swatch)

        delete_btn = QToolButton()
        delete_btn.setObjectName("layerDeleteBtn")
        delete_btn.setIcon(icon_manager.get("layer_row_delete", size=ICON_SM, color=Color.TEXT_FAINT))
        delete_btn.setIconSize(QSize(ICON_SM, ICON_SM))
        delete_btn.setEnabled(deletable)
        delete_btn.setToolTip("Delete layer" if deletable else 'Layer "0" cannot be deleted')
        delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        delete_btn.clicked.connect(lambda: self.deleteRequested.emit(name))
        layout.addWidget(delete_btn)


class LayerTab(QWidget):

    layers_changed = pyqtSignal()

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._layers, self._default_name = self._load(settings)

        layout = SectionColumn(self)

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(2)
        layout.addWidget(self._rows_container)

        add_btn = QToolButton()
        add_btn.setObjectName("layerAddBtn")
        add_btn.setIcon(icon_manager.get("layer_add", size=ICON_SM, color=Color.TEXT_MUTED))
        add_btn.setIconSize(QSize(ICON_SM, ICON_SM))
        add_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        add_btn.setText("Add layer")
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_clicked)
        layout.addWidget(add_btn)
        layout.addStretch(1)

        self._rebuild_rows()

    # -- reading ----------------------------------------------------------
    def layer_names(self) -> List[str]:
        return [name for name, _rgb in self._layers]

    def get_rgb(self, name: str) -> Tuple[int, int, int]:
        for layer_name, rgb in self._layers:
            if layer_name == name:
                return rgb
        return DEFAULT_LAYER_RGB

    def default_layer_name(self) -> str:
        return self._default_name if self._default_name in self.layer_names() else DEFAULT_LAYER_NAME

    # -- editing ------------------------------------------------------------
    def _on_add_clicked(self) -> None:
        name, ok = QInputDialog.getText(self, "New Layer", "Layer name:")
        name = name.strip()
        if not ok or not name or name in self.layer_names():
            return
        rgb = _AUTO_PALETTE[len(self._layers) % len(_AUTO_PALETTE)]
        self._layers.append((name, rgb))
        self._rebuild_rows()
        self.layers_changed.emit()

    def _on_delete(self, name: str) -> None:
        if name == DEFAULT_LAYER_NAME or len(self._layers) <= 1:
            return
        self._layers = [(n, rgb) for n, rgb in self._layers if n != name]
        if self._default_name == name:
            self._default_name = self._layers[0][0]
        self._rebuild_rows()
        self.layers_changed.emit()

    def _on_color_changed(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self._layers = [(n, rgb if n == name else old_rgb) for n, old_rgb in self._layers]
        self.layers_changed.emit()

    def _on_set_default(self, name: str) -> None:
        if self._default_name == name:
            return
        self._default_name = name
        self._rebuild_rows()
        self.layers_changed.emit()

    def _rebuild_rows(self) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        deletable = len(self._layers) > 1
        for name, rgb in self._layers:
            row = _LayerDefRow(name, rgb, name == self._default_name, name != DEFAULT_LAYER_NAME and deletable)
            row.defaultRequested.connect(self._on_set_default)
            row.colorRequested.connect(self._on_color_changed)
            row.deleteRequested.connect(self._on_delete)
            self._rows_layout.addWidget(row)

    # -- project save/load --------------------------------------------------
    def get_state(self) -> Tuple[List[Tuple[str, Tuple[int, int, int]]], str]:
        return list(self._layers), self._default_name

    def set_state(self, layers: List[Tuple[str, Tuple[int, int, int]]], default_name: str) -> None:
        self._layers = list(layers) or [(DEFAULT_LAYER_NAME, DEFAULT_LAYER_RGB)]
        self._default_name = default_name if default_name in self.layer_names() else self._layers[0][0]
        self._rebuild_rows()

    # -- QSettings persistence (last-used default, across projects) --------
    def _load(self, settings: QSettings) -> Tuple[List[Tuple[str, Tuple[int, int, int]]], str]:
        raw = settings.value(SETTINGS_KEY, None)
        if raw:
            try:
                payload = json.loads(str(raw))
                layers = [(str(name), tuple(rgb)) for name, rgb in payload["layers"]]
                if layers:
                    return layers, str(payload.get("default_name", layers[0][0]))
            except (ValueError, KeyError, TypeError):
                pass
        return [(DEFAULT_LAYER_NAME, DEFAULT_LAYER_RGB)], DEFAULT_LAYER_NAME

    def persist(self, settings: QSettings) -> None:
        settings.setValue(SETTINGS_KEY, json.dumps({"layers": self._layers, "default_name": self._default_name}))

    def is_modified(self) -> bool:
        return self._layers != [(DEFAULT_LAYER_NAME, DEFAULT_LAYER_RGB)] or self._default_name != DEFAULT_LAYER_NAME
