from __future__ import annotations

from ui.theme.tokens import (
    Color,
    FONT_FAMILY,
    MONO_FONT_FAMILY,
    RADIUS,
    RADIUS_LG,
    RADIUS_SM,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXL,
    TEXT_LG,
    TEXT_MD,
    TEXT_SM,
    TEXT_XL,
    TEXT_XS,
)


def build_stylesheet() -> str:
    c = Color
    return f"""
/* ---------- base ---------- */
QMainWindow, QWidget {{
    background: {c.APP_BG};
    color: {c.TEXT};
    font-family: "{FONT_FAMILY}", "Segoe UI", sans-serif;
    font-size: {TEXT_MD}px;
}}
QWidget:disabled {{ color: {c.TEXT_FAINT}; }}
QToolTip {{
    background: {c.SURFACE_RAISED};
    color: {c.TEXT};
    border: 1px solid {c.BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_XS}px {SPACE_SM}px;
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c.BORDER_STRONG}; border-radius: 5px; min-height: 24px; }}
QScrollBar::handle:vertical:hover {{ background: {c.TEXT_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}

/* ---------- main splitter (drag to resize the left column) ---------- */
QSplitter#mainSplitter::handle {{ background: transparent; width: {SPACE_LG}px; }}
QSplitter#mainSplitter::handle:hover {{ background: {c.ACCENT_SOFT}; }}

/* ---------- top bar ---------- */
#topBar {{ background: {c.APP_BG}; border-bottom: 1px solid {c.BORDER}; }}
#topBarLogo {{ padding: 0; }}
#demoStateLabel {{
    color: {c.TEXT_FAINT};
    font-size: {TEXT_XS}px;
    font-weight: 600;
    letter-spacing: 1px;
}}

/* ---------- dropdown menus (e.g. the top bar's File menu) ---------- */
QMenu {{
    background: {c.SURFACE_RAISED};
    border: 1px solid {c.BORDER_STRONG};
    border-radius: {RADIUS}px;
    padding: {SPACE_XS}px;
    color: {c.TEXT};
}}
QMenu::item {{
    padding: {SPACE_SM}px {SPACE_LG}px;
    border-radius: {RADIUS_SM}px;
}}
QMenu::item:selected {{ background: {c.ACCENT_SOFT}; color: {c.TEXT}; }}
QMenu::item:disabled {{ color: {c.TEXT_FAINT}; }}
QMenu::separator {{ height: 1px; background: {c.BORDER}; margin: {SPACE_XS}px {SPACE_SM}px; }}
QMenu::right-arrow {{ width: 10px; height: 10px; }}

/* ---------- tags ---------- */
QLabel#tag {{
    border-radius: {RADIUS_SM}px;
    padding: 1px {SPACE_SM}px;
    font-size: {TEXT_XS}px;
    font-weight: 600;
    border: 1px solid {c.BORDER};
    color: {c.TEXT_MUTED};
    background: {c.SURFACE_RAISED};
}}
QLabel#tag[variant="accent"] {{ color: {c.ACCENT}; border-color: {c.ACCENT_BORDER}; background: {c.ACCENT_SOFT}; }}
QLabel#tag[variant="success"] {{ color: {c.SUCCESS}; border-color: {c.SUCCESS}; background: rgba(127, 207, 158, 0.12); }}
QLabel#tag[variant="error"] {{ color: {c.ERROR}; border-color: {c.ERROR_BORDER}; background: {c.ERROR_BG}; }}

/* ---------- segmented control ---------- */
#segmented {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS}px;
}}
QPushButton#segBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_XS}px {SPACE_MD}px;
    color: {c.TEXT_MUTED};
    font-size: {TEXT_SM}px;
}}
QPushButton#segBtn:hover {{ color: {c.TEXT}; }}
QPushButton#segBtn:checked {{
    background: {c.ACCENT_SOFT};
    border: 1px solid {c.ACCENT_BORDER};
    color: {c.ACCENT};
    font-weight: 600;
}}
QPushButton#segBtn:disabled {{ color: {c.TEXT_FAINT}; }}

/* ---------- radio cards (drawing mode) ---------- */
QPushButton#radioCard {{
    text-align: left;
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS}px;
    padding: {SPACE_SM}px {SPACE_MD}px;
    color: {c.TEXT_MUTED};
}}
QPushButton#radioCard:hover {{ border-color: {c.BORDER_STRONG}; color: {c.TEXT}; }}
QPushButton#radioCard:checked {{
    border: 1px solid {c.ACCENT_BORDER};
    color: {c.TEXT};
    background: {c.ACCENT_SOFT};
}}

/* ---------- cards / panels ---------- */
QFrame#card {{
    background: {c.SURFACE};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_LG}px;
}}

/* ---------- drop zone ---------- */
#dropZone {{
    background: {c.SURFACE_SUNKEN};
    border: 1.5px dashed {c.BORDER_STRONG};
    border-radius: {RADIUS_LG}px;
}}
#dropZoneHint {{ color: {c.TEXT_MUTED}; font-size: {TEXT_SM}px; }}

/* ---------- file card ---------- */
#fileCard {{
    background: {c.SURFACE};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_LG}px;
}}
#fileCardName {{ font-weight: 600; color: {c.TEXT}; }}
#fileCardMeta {{ color: {c.TEXT_MUTED}; font-size: {TEXT_SM}px; }}
QPushButton#linkButton {{
    background: transparent;
    border: none;
    color: {c.ACCENT};
    font-size: {TEXT_SM}px;
    padding: 2px;
}}
QPushButton#linkButton:hover {{ text-decoration: underline; }}

/* ---------- dxf source row ---------- */
#dxfSourceRow {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS}px;
}}
#dxfSourceTitle {{ color: {c.TEXT}; font-weight: 600; font-size: {TEXT_SM}px; }}
#dxfSourceSubtitle {{ color: {c.TEXT_MUTED}; font-size: {TEXT_XS}px; }}
#dxfSourceSubtitle[variant="error"] {{ color: {c.ERROR}; }}

/* ---------- dxf toolbar ---------- */
#dxfToolbar {{ background: transparent; }}
QToolButton#dxfToolBtn {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_XS}px {SPACE_SM}px;
    color: {c.TEXT_MUTED};
    font-size: {TEXT_MD}px;
    min-width: 26px;
    min-height: 26px;
}}
QToolButton#dxfToolBtn:hover {{ background: {c.SURFACE_HOVER}; color: {c.TEXT}; }}
QToolButton#dxfToolBtn:checked {{
    background: {c.ACCENT_SOFT};
    border: 1px solid {c.ACCENT_BORDER};
    color: {c.ACCENT};
}}
QToolButton#dxfToolBtn:disabled {{ color: {c.TEXT_FAINT}; }}
QFrame#dxfToolbarSeparator {{ background: {c.BORDER}; max-width: 1px; margin: {SPACE_XS}px {SPACE_XS}px; }}

/* ---------- layers panel ---------- */
#layerPanelTitle {{ color: {c.TEXT_MUTED}; font-weight: 600; font-size: {TEXT_SM}px; }}
QFrame#layerRow {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-left: 2px solid transparent;
    border-radius: {RADIUS_SM}px;
}}
QFrame#layerRow[active="true"] {{
    border-left: 2px solid {c.ACCENT};
    background: {c.SURFACE_HOVER};
}}
QToolButton#layerActiveBtn {{
    background: transparent;
    border: none;
    color: {c.ACCENT};
    font-size: {TEXT_SM}px;
    padding: 0;
    min-width: 14px;
}}
QToolButton#layerNameBtn {{
    background: transparent;
    border: none;
    color: {c.TEXT};
    font-size: {TEXT_XS}px;
    text-align: left;
    padding: 0;
}}
QToolButton#layerNameBtn:hover {{ color: {c.ACCENT}; }}
QToolButton#layerColorSwatch {{
    border: 1px solid {c.BORDER_STRONG};
    border-radius: 3px;
    min-width: 14px;
    max-width: 14px;
    min-height: 14px;
    max-height: 14px;
    padding: 0;
}}
QToolButton#colorSwatchBtn {{
    border: 1px solid {c.BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    padding: 0;
}}
QToolButton#colorSwatchBtn:hover {{ border-color: {c.ACCENT_BORDER}; }}
QCheckBox#layerVisibleCheck {{ spacing: 0; }}
QCheckBox#layerVisibleCheck::indicator {{
    width: 12px;
    height: 12px;
    border: 1px solid {c.BORDER_STRONG};
    border-radius: 3px;
    background: {c.SURFACE_SUNKEN};
}}
QCheckBox#layerVisibleCheck::indicator:checked {{
    background: {c.ACCENT};
    border: 1px solid {c.ACCENT};
}}
QToolButton#layerDeleteBtn {{
    background: transparent;
    border: none;
    color: {c.TEXT_FAINT};
    font-size: {TEXT_XS}px;
    padding: 0;
    min-width: 14px;
}}
QToolButton#layerDeleteBtn:hover:enabled {{ color: {c.ERROR}; }}
QToolButton#layerDeleteBtn:disabled {{ color: {c.BORDER}; }}
QToolButton#layerAddBtn {{
    background: transparent;
    border: 1px dashed {c.BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    color: {c.TEXT_MUTED};
    font-size: {TEXT_XS}px;
    padding: {SPACE_XS}px;
}}
QToolButton#layerAddBtn:hover {{ color: {c.ACCENT}; border-color: {c.ACCENT_BORDER}; }}
QToolButton#layerPruneBtn {{
    background: transparent;
    border: 1px dashed {c.BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
    color: {c.TEXT_MUTED};
    font-size: {TEXT_XS}px;
    padding: {SPACE_XS}px;
}}
QToolButton#layerPruneBtn:hover:enabled {{ color: {c.ACCENT}; border-color: {c.ACCENT_BORDER}; }}
QToolButton#layerPruneBtn:disabled {{ color: {c.BORDER}; border-color: {c.BORDER}; }}

/* ---------- dxf preview canvas ---------- */
#sheetTabBar {{ background: transparent; }}
QToolButton#sheetTab {{
    background: {c.SURFACE};
    border: 1px solid {c.BORDER};
    border-bottom: none;
    border-top-left-radius: {RADIUS_SM}px;
    border-top-right-radius: {RADIUS_SM}px;
    padding: {SPACE_XS}px {SPACE_LG}px;
    color: {c.TEXT_MUTED};
}}
QToolButton#sheetTab:hover {{ background: {c.SURFACE_HOVER}; color: {c.TEXT}; }}
QToolButton#sheetTab[active="true"] {{
    background: {c.SURFACE_RAISED};
    border: 1px solid {c.ACCENT_BORDER};
    border-bottom: none;
    color: {c.TEXT};
}}
QToolButton#sheetTabAdd {{
    background: transparent;
    border: none;
    padding: {SPACE_XS}px {SPACE_SM}px;
}}
QToolButton#sheetTabAdd:hover {{ background: {c.SURFACE_HOVER}; border-radius: {RADIUS_SM}px; }}
QToolButton#sheetRow {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_SM}px {SPACE_MD}px;
    color: {c.TEXT_MUTED};
    text-align: left;
}}
QToolButton#sheetRow:hover {{ background: {c.SURFACE_HOVER}; color: {c.TEXT}; }}
QToolButton#sheetRow[active="true"] {{
    border: 1px solid {c.ACCENT_BORDER};
    background: {c.ACCENT_SOFT};
    color: {c.TEXT};
}}
#dxfCanvas {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-bottom: none;
    border-top-left-radius: {RADIUS}px;
    border-top-right-radius: {RADIUS}px;
}}
#dxfEmpty {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS}px;
}}
#dxfEmptyText {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; }}

/* ---------- dxf command line ---------- */
#dxfCommandLine {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-bottom-left-radius: {RADIUS}px;
    border-bottom-right-radius: {RADIUS}px;
}}
QPlainTextEdit#dxfCommandHistory {{
    background: {c.SURFACE_SUNKEN};
    border: none;
    border-bottom: 1px solid {c.BORDER};
    border-radius: 0;
    color: {c.TEXT_MUTED};
    font-family: "{MONO_FONT_FAMILY}", "Consolas", monospace;
    font-size: {TEXT_XS}px;
    padding: {SPACE_XS}px {SPACE_SM}px;
}}
#dxfCommandInputRow {{ background: {c.SURFACE_SUNKEN}; border-bottom-left-radius: {RADIUS}px; border-bottom-right-radius: {RADIUS}px; }}
#dxfCommandPrompt {{
    color: {c.TEXT_FAINT};
    font-family: "{MONO_FONT_FAMILY}", "Consolas", monospace;
    font-size: {TEXT_SM}px;
    background: transparent;
}}
QLineEdit#dxfCommandInput {{
    background: {c.SURFACE_SUNKEN};
    border: none;
    color: {c.TEXT};
    font-family: "{MONO_FONT_FAMILY}", "Consolas", monospace;
    font-size: {TEXT_SM}px;
}}

/* ---------- text options bar (floats above a selected TEXT entity) ---------- */
QFrame#textOptionsBar {{
    background: {c.SURFACE_RAISED};
    border: 1px solid {c.BORDER_STRONG};
    border-radius: {RADIUS_SM}px;
}}
QLineEdit#textOptionsContent, QLineEdit#textOptionsField {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_SM}px;
    color: {c.TEXT};
    font-size: {TEXT_SM}px;
    padding: {SPACE_XS}px {SPACE_SM}px;
}}
QLineEdit#textOptionsContent:focus, QLineEdit#textOptionsField:focus {{ border-color: {c.ACCENT_BORDER}; }}

/* ---------- accordion ---------- */
QFrame#accordionHeader {{
    background: transparent;
    border: none;
    border-top: 1px solid {c.BORDER};
    border-left: 2px solid transparent;
}}
QFrame#accordionHeader:hover {{ background: {c.SURFACE_HOVER}; }}
QFrame#accordionHeader[expanded="true"] {{
    background: {c.SURFACE_HOVER};
    border-left: 2px solid {c.ACCENT};
}}
#accordionIcon {{ min-width: 16px; }}
#accordionTitle {{ color: {c.TEXT}; font-weight: 600; font-size: {TEXT_MD}px; }}
QWidget#accordionContent {{
    background: transparent;
    border-left: 2px solid transparent;
    padding: {SPACE_SM}px {SPACE_LG}px {SPACE_LG}px {SPACE_LG}px;
}}

/* ---------- fields ---------- */
QLabel#fieldLabel {{ color: {c.TEXT_MUTED}; font-size: {TEXT_SM}px; }}
QLineEdit#input, QPlainTextEdit#input {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_SM}px;
    color: {c.TEXT};
    selection-background-color: {c.ACCENT_SOFT};
}}
QLineEdit#input:focus, QPlainTextEdit#input:focus {{ border: 1px solid {c.ACCENT_BORDER}; }}
QLineEdit#input:disabled, QPlainTextEdit#input:disabled {{ color: {c.TEXT_FAINT}; }}
QComboBox#layerDropdown, QComboBox#dropdown {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_SM}px;
    color: {c.TEXT};
}}
QComboBox#layerDropdown:focus, QComboBox#dropdown:focus {{ border: 1px solid {c.ACCENT_BORDER}; }}
QComboBox#layerDropdown::drop-down, QComboBox#dropdown::drop-down {{ border: none; width: 20px; }}
QComboBox#layerDropdown QAbstractItemView, QComboBox#dropdown QAbstractItemView {{
    background: {c.SURFACE_RAISED};
    border: 1px solid {c.BORDER_STRONG};
    color: {c.TEXT};
    selection-background-color: {c.ACCENT_SOFT};
    outline: none;
}}

QPushButton#checkField {{
    text-align: left;
    background: transparent;
    border: none;
    padding: {SPACE_XS}px 0;
    color: {c.TEXT_MUTED};
    font-size: {TEXT_MD}px;
}}
QPushButton#checkField:hover {{ color: {c.TEXT}; }}
QPushButton#checkField:checked {{ color: {c.ACCENT}; }}

/* ---------- buttons ---------- */
QPushButton#btn {{
    border-radius: {RADIUS}px;
    padding: {SPACE_SM}px {SPACE_LG}px;
    font-size: {TEXT_MD}px;
    font-weight: 600;
}}
QPushButton#btn[variant="primary"] {{
    background: transparent;
    border: 1.5px solid {c.ACCENT};
    color: {c.ACCENT};
}}
QPushButton#btn[variant="primary"]:hover {{ background: {c.ACCENT_SOFT}; }}
QPushButton#btn[variant="primary"]:disabled {{ border-color: {c.BORDER}; color: {c.TEXT_FAINT}; }}

QPushButton#btn[variant="secondary"] {{
    background: {c.SURFACE_RAISED};
    border: 1px solid {c.BORDER};
    color: {c.TEXT};
}}
QPushButton#btn[variant="secondary"]:hover {{ border-color: {c.BORDER_STRONG}; }}
QPushButton#btn[variant="secondary"]:disabled {{ color: {c.TEXT_FAINT}; border-color: {c.BORDER}; }}
/* The dropdown arrow for a #btn with a menu attached (e.g. "File  ▾") is
   drawn as part of the button's own text instead - suppress Qt's native
   indicator so there's only ever one arrow, styled consistently. */
QPushButton#btn::menu-indicator {{ image: none; width: 0px; }}

/* ---------- dxf preview header ---------- */
#previewHeaderTitle {{ font-weight: 600; font-size: {TEXT_MD}px; color: {c.TEXT}; }}
#previewMeta {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; }}

#errorBanner {{
    background: {c.ERROR_BG};
    border: 1px solid {c.ERROR_BORDER};
    border-radius: {RADIUS}px;
}}
#errorBannerText {{ color: {c.ERROR}; font-size: {TEXT_SM}px; }}

/* ---------- status bar ---------- */
#statusBar {{ background: {c.APP_BG}; border-top: 1px solid {c.BORDER}; }}
#statusText {{ color: {c.TEXT_FAINT}; font-size: {TEXT_XS}px; }}
#statusText[variant="error"] {{ color: {c.ERROR}; font-weight: 600; }}

/* ---------- start screen (project launcher) ---------- */
#startSidebar {{
    background: {c.SURFACE};
    border-right: 1px solid {c.BORDER};
}}
#startTitle {{ font-size: {TEXT_XL}px; font-weight: 600; color: {c.TEXT}; }}
#startLogo {{ padding: 0; }}
#startHeading {{ font-size: {TEXT_LG}px; font-weight: 600; color: {c.TEXT}; }}
#startEmpty {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; padding: {SPACE_XXL}px; }}
QTableWidget#startTable {{
    background: transparent;
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS}px;
    gridline-color: {c.BORDER};
    color: {c.TEXT};
    selection-background-color: {c.ACCENT_SOFT};
    selection-color: {c.TEXT};
}}
QTableWidget#startTable::item {{ padding: {SPACE_SM}px; border-bottom: 1px solid {c.BORDER}; }}
QTableWidget#tableStructureGrid {{
    background: {c.SURFACE};
    border: 1px solid {c.TEXT};
    gridline-color: {c.TEXT};
    color: {c.TEXT};
    selection-background-color: {c.ACCENT_SOFT};
    selection-color: {c.TEXT};
}}
QTableWidget#tableStructureGrid::item {{ padding: {SPACE_SM}px; }}
QHeaderView::section {{
    background: {c.SURFACE_RAISED};
    color: {c.TEXT_MUTED};
    padding: {SPACE_SM}px;
    border: none;
    border-bottom: 1px solid {c.BORDER_STRONG};
    font-size: {TEXT_SM}px;
    font-weight: 600;
}}
"""


APP_STYLESHEET = build_stylesheet()
