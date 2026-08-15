"""Application-wide Qt stylesheet for the "Nocturne" visual system.

Built from the tokens in ui/theme.py so every widget agrees on color, radius
and spacing. The accent color is used as an outline / dot / text color and,
deliberately, almost never as a fill — the sanctioned exceptions are the
completed step in WorkflowStepper and the soft accent wash behind a selected
segmented-control / radio-card option.
"""
from __future__ import annotations

from ui.theme import (
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

/* ---------- top bar ---------- */
#topBar {{ background: {c.APP_BG}; border-bottom: 1px solid {c.BORDER}; }}
#appTitle {{ font-size: {TEXT_XL}px; font-weight: 600; color: {c.TEXT}; }}
#demoStateLabel {{
    color: {c.TEXT_FAINT};
    font-size: {TEXT_XS}px;
    font-weight: 600;
    letter-spacing: 1px;
}}

/* ---------- workflow stepper ---------- */
#stepper {{ background: {c.APP_BG}; border-bottom: 1px solid {c.BORDER}; }}
QLabel#stepCircle {{
    border-radius: 11px;
    border: 1px solid {c.BORDER_STRONG};
    color: {c.TEXT_FAINT};
    font-weight: 700;
    font-size: {TEXT_SM}px;
    background: transparent;
}}
QLabel#stepCircle[state="done"] {{
    background: {c.ACCENT};
    border: 1px solid {c.ACCENT};
    color: {c.APP_BG};
}}
QLabel#stepCircle[state="active"] {{
    border: 1.5px solid {c.ACCENT};
    color: {c.ACCENT};
    background: {c.ACCENT_SOFT};
}}
QLabel#stepCircle[state="upcoming"] {{
    border: 1px solid {c.BORDER};
    color: {c.TEXT_FAINT};
    background: transparent;
}}
QLabel#stepCircle[state="error"] {{
    border: 1.5px solid {c.ERROR};
    color: {c.ERROR};
    background: {c.ERROR_BG};
}}
QLabel#stepLabel {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; }}
QLabel#stepLabel[state="done"], QLabel#stepLabel[state="active"] {{ color: {c.TEXT}; font-weight: 600; }}
QLabel#stepLabel[state="error"] {{ color: {c.ERROR}; font-weight: 600; }}
QFrame#stepLine {{ background: {c.BORDER}; border: none; }}
QFrame#stepLine[done="true"] {{ background: {c.ACCENT_BORDER}; }}

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
#dropZoneIcon {{ font-size: 26px; color: {c.TEXT_FAINT}; }}
#dropZoneHint {{ color: {c.TEXT_MUTED}; font-size: {TEXT_SM}px; }}

/* ---------- file card ---------- */
#fileCard {{
    background: {c.SURFACE};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_LG}px;
}}
#fileCardIcon {{ font-size: 22px; }}
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
#dxfSourceIcon {{ font-size: 18px; color: {c.TEXT_MUTED}; }}
#dxfSourceTitle {{ color: {c.TEXT}; font-weight: 600; font-size: {TEXT_SM}px; }}
#dxfSourceSubtitle {{ color: {c.TEXT_MUTED}; font-size: {TEXT_XS}px; }}
#dxfSourceSubtitle[variant="error"] {{ color: {c.ERROR}; }}

/* ---------- dxf preview canvas ---------- */
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
#dxfEmptyIcon {{ font-size: 24px; color: {c.TEXT_FAINT}; }}
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
#accordionIcon {{ color: {c.TEXT_MUTED}; font-size: {TEXT_MD}px; min-width: 16px; }}
#accordionTitle {{ color: {c.TEXT}; font-weight: 600; font-size: {TEXT_MD}px; }}
#accordionDot {{ color: {c.ACCENT}; font-size: 8px; }}
#accordionChevron {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; }}
QWidget#accordionContent {{
    background: transparent;
    border-left: 2px solid transparent;
    padding: {SPACE_SM}px {SPACE_LG}px {SPACE_LG}px {SPACE_LG}px;
}}

/* ---------- fields ---------- */
QLabel#fieldLabel {{ color: {c.TEXT_MUTED}; font-size: {TEXT_SM}px; }}
QLineEdit#input {{
    background: {c.SURFACE_SUNKEN};
    border: 1px solid {c.BORDER};
    border-radius: {RADIUS_SM}px;
    padding: {SPACE_SM}px;
    color: {c.TEXT};
    selection-background-color: {c.ACCENT_SOFT};
}}
QLineEdit#input:focus {{ border: 1px solid {c.ACCENT_BORDER}; }}
QLineEdit#input:disabled {{ color: {c.TEXT_FAINT}; }}

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

/* ---------- dxf preview header ---------- */
#previewHeaderTitle {{ font-weight: 600; font-size: {TEXT_MD}px; color: {c.TEXT}; }}
#previewMeta {{ color: {c.TEXT_FAINT}; font-size: {TEXT_SM}px; }}

#errorBanner {{
    background: {c.ERROR_BG};
    border: 1px solid {c.ERROR_BORDER};
    border-radius: {RADIUS}px;
}}
#errorBannerIcon {{ color: {c.ERROR}; font-size: {TEXT_MD}px; }}
#errorBannerText {{ color: {c.ERROR}; font-size: {TEXT_SM}px; }}

/* ---------- status bar ---------- */
#statusBar {{ background: {c.APP_BG}; border-top: 1px solid {c.BORDER}; }}
#statusText {{ color: {c.TEXT_FAINT}; font-size: {TEXT_XS}px; }}
#statusText[variant="error"] {{ color: {c.ERROR}; font-weight: 600; }}
"""


APP_STYLESHEET = build_stylesheet()
