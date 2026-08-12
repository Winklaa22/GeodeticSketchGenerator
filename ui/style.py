"""Application-wide Qt stylesheet."""
from __future__ import annotations

APP_STYLESHEET = """
QMainWindow { background: #0b0c0e; }
QWidget { color: #e5e7eb; font-size: 13px; }
QGroupBox { background-color: #1f2937;  border: 1px solid #27272a; border-radius: 10px; padding: 10px; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #a1a1aa; }
QLabel { color: #e5e7eb; }
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: #111827; border: 1px solid #374151; border-radius: 8px; padding: 6px; color: #e5e7eb; }
QPushButton { background: #16a34a; border: none; border-radius: 10px; padding: 8px 12px; color: white; font-weight: 600; }
QPushButton:hover { background: #22c55e; }
QPushButton:disabled { background: #374151; color: #9ca3af; }
QTabBar::tab { background: #111827; padding: 6px 10px; border-top-left-radius: 8px; border-top-right-radius: 8px; color: #d1d5db; }
QTabBar::tab:selected { background: #1f2937; }
QStatusBar { color: #94a3b8; }
"""
