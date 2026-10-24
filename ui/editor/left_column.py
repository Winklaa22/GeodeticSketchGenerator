from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QScrollArea, QStackedWidget, QVBoxLayout, QWidget

from ui.theme import LEFT_COLUMN_MAX_WIDTH, LEFT_COLUMN_MIN_WIDTH, SPACE_LG
from ui.widgets import DxfSourceRow, SegmentedControl


def _scroll_area(content: QWidget) -> QScrollArea:
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setWidget(content)
    return scroll


def _with_footer(scroll: QScrollArea, footer: Optional[QWidget]) -> QWidget:
    if footer is None:
        return scroll
    page = QWidget()
    column = QVBoxLayout(page)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(SPACE_LG)
    column.addWidget(scroll, 1)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    row.addWidget(footer)
    row.addStretch(1)
    column.addLayout(row)
    return page


class LeftColumn(QWidget):

    def __init__(
        self,
        pages: Sequence[Tuple[str, str, QWidget]],
        footers: Optional[Dict[str, QWidget]] = None,
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
        footers = footers or {}
        self._indexes = {
            key: self._stack.addWidget(_with_footer(_scroll_area(page), footers.get(key)))
            for key, _label, page in pages
        }
        self._nav.currentChanged.connect(lambda key: self._stack.setCurrentIndex(self._indexes[key]))
        layout.addWidget(self._stack, 1)

    def show_page(self, key: str) -> None:
        self._nav.setCurrent(key)
        self._stack.setCurrentIndex(self._indexes[key])
