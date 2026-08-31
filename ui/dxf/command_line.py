from __future__ import annotations

from typing import Optional

from PyQt6 import QtCore as qc, QtWidgets as qw

from ui.theme import SPACE_SM, SPACE_XS


class CommandLine(qw.QWidget):

    commandEntered = qc.pyqtSignal(str)
    undoRequested = qc.pyqtSignal()
    redoRequested = qc.pyqtSignal()

    def __init__(self, parent: Optional[qw.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("dxfCommandLine")
        layout = qw.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._history = qw.QPlainTextEdit()
        self._history.setObjectName("dxfCommandHistory")
        self._history.setReadOnly(True)
        self._history.setFixedHeight(52)
        self._history.setLineWrapMode(qw.QPlainTextEdit.LineWrapMode.NoWrap)
        self._history.setVerticalScrollBarPolicy(qc.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history.setFocusPolicy(qc.Qt.FocusPolicy.NoFocus)
        layout.addWidget(self._history)

        input_row = qw.QWidget()
        input_row.setObjectName("dxfCommandInputRow")
        input_layout = qw.QHBoxLayout(input_row)
        input_layout.setContentsMargins(SPACE_SM, SPACE_XS, SPACE_SM, SPACE_XS)
        input_layout.setSpacing(SPACE_XS)
        prompt = qw.QLabel("Command:")
        prompt.setObjectName("dxfCommandPrompt")
        self._input = qw.QLineEdit()
        self._input.setObjectName("dxfCommandInput")
        self._input.setPlaceholderText("POINT, TEXT, LINE, CIRCLE, PIPE, ZOOM …")
        self._input.returnPressed.connect(self._submit)
        self._input.installEventFilter(self)
        input_layout.addWidget(prompt)
        input_layout.addWidget(self._input, 1)
        layout.addWidget(input_row)

        self.reset()

    def eventFilter(self, obj: qc.QObject, event: qc.QEvent) -> bool:
        if obj is self._input and event.type() == qc.QEvent.Type.KeyPress:
            key_event = event
            if key_event.modifiers() & qc.Qt.KeyboardModifier.ControlModifier:
                is_shift = bool(key_event.modifiers() & qc.Qt.KeyboardModifier.ShiftModifier)
                if key_event.key() == qc.Qt.Key.Key_Z and not is_shift:
                    self.undoRequested.emit()
                    return True
                if key_event.key() == qc.Qt.Key.Key_Y or (key_event.key() == qc.Qt.Key.Key_Z and is_shift):
                    self.redoRequested.emit()
                    return True
        return super().eventFilter(obj, event)

    def reset(self) -> None:
        self._history.clear()
        self._echo("Type POINT, TEXT, LINE, CIRCLE, PIPE, ERASE, U(ndo), REDO, ZOOM, PAN or REGEN.")

    def show_response(self, message: str) -> None:
        if message:
            self._echo(message)

    def set_placeholder(self, text: str) -> None:
        self._input.setPlaceholderText(text)

    def focus_input(self) -> None:
        self._input.setFocus()

    def _submit(self) -> None:
        text = self._input.text().strip()
        self._input.clear()
        if not text:
            return
        self._echo(f"Command: {text}")
        self.commandEntered.emit(text)

    def _echo(self, line: str) -> None:
        self._history.appendPlainText(line)
        scrollbar = self._history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

