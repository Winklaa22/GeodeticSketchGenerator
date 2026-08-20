"""Layer accordion section."""
from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import QSettings, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QWidget

from ui.theme import SPACE_SM
from ui.widgets import ColorSwatchButton, SectionColumn, make_field, styled_line_edit

DEFAULT_LAYER_NAME = "0"
# Same family as the app's own accent color - a reasonable default for a
# layer that doesn't exist yet, distinct from ezdxf's own plain-white default.
DEFAULT_LAYER_RGB: Tuple[int, int, int] = (145, 132, 217)
SETTINGS_KEY = "layer"
SETTINGS_COLOR_KEY = "layer_color"


def _load_rgb(settings: QSettings) -> Tuple[int, int, int]:
    raw = settings.value(SETTINGS_COLOR_KEY, None)
    if raw:
        try:
            r, g, b = (int(part) for part in str(raw).split(","))
            if all(0 <= value <= 255 for value in (r, g, b)):
                return (r, g, b)
        except ValueError:
            pass
    return DEFAULT_LAYER_RGB


class LayerTab(QWidget):

    layer_changed = pyqtSignal()

    def __init__(self, settings: QSettings, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = SectionColumn(self)

        self.layer_input = styled_line_edit(settings.value(SETTINGS_KEY, DEFAULT_LAYER_NAME))
        self.layer_input.setPlaceholderText("Enter layer name")
        self.layer_input.textChanged.connect(lambda _t: self.layer_changed.emit())

        self.color_swatch = ColorSwatchButton(_load_rgb(settings), tooltip="Color for the target layer")
        self.color_swatch.colorChanged.connect(lambda _rgb: self.layer_changed.emit())

        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(SPACE_SM)
        row_layout.addWidget(self.layer_input, 1)
        row_layout.addWidget(self.color_swatch)
        layout.addWidget(make_field("Layer name", row))
        layout.addStretch(1)

    def get_layer_name(self) -> str:
        return self.layer_input.text()

    def get_layer_rgb(self) -> Tuple[int, int, int]:
        """The color the target layer should end up with on Apply."""
        return self.color_swatch.rgb

    def set_state(self, name: str, rgb: Tuple[int, int, int]) -> None:
        self.layer_input.setText(name)
        self.color_swatch.set_color(rgb)

    def persist(self, settings: QSettings) -> None:
        settings.setValue(SETTINGS_KEY, self.layer_input.text())
        settings.setValue(SETTINGS_COLOR_KEY, ",".join(str(value) for value in self.color_swatch.rgb))

    def is_modified(self) -> bool:
        return self.layer_input.text() != DEFAULT_LAYER_NAME or self.color_swatch.rgb != DEFAULT_LAYER_RGB
