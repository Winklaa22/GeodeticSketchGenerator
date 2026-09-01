from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PyQt6.QtWidgets import QFrame, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ui.theme import LEFT_COLUMN_MAX_WIDTH, LEFT_COLUMN_MIN_WIDTH, SPACE_LG
from ui.widgets import DxfSourceRow, SegmentedControl


def _scroll_area(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


class LeftColumn(QWidget):

    def __init__(
        self,
        pages: Sequence[Tuple[str, str, QWidget]],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setMinimumWidth(LEFT_COLUMN_MIN_WIDTH)
        self.setMaximumWidth(LEFT_COLUMN_MAX_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_LG)

        self.dxf_source_row = DxfSourceRow()
        layout.addWidget(self.dxf_source_row)

        self._nav = SegmentedControl([(key, label) for key, label, _page in pages])
        layout.addWidget(self._nav)

        self._stack = QStackedWidget()
        indexes = {key: self._stack.addWidget(_scroll_area(page)) for key, _label, page in pages}
        self._nav.currentChanged.connect(lambda key: self._stack.setCurrentIndex(indexes[key]))
        layout.addWidget(self._stack, 1)
