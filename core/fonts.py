from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from ezdxf.fonts import fonts as ezdxf_fonts

# fontTools (ezdxf's TTF/OTF parser) warns whenever a font file's embedded "created"/
# "modified" timestamp looks implausible - harmless (some of the substitute fonts loaded
# by ensure_font_renders_distinctly below happen to have one), but noisy since this app
# never configures logging and Python's default handler prints every such warning to the
# terminal.
logging.getLogger("fontTools").setLevel(logging.ERROR)


@dataclass(frozen=True)
class FontSpec:

    id: str
    label: str
    font_file: str
    category: str
    # Real, commonly-installed font families to substitute when this exact font file
    # isn't found on the current machine (true for "romans.shx"/"arial.ttf"/etc. on
    # almost anything but Windows with AutoCAD installed) - without this, ezdxf silently
    # renders every unresolved font as the same single fallback face, so switching fonts
    # in the UI would visibly do nothing. The DXF file itself always keeps the literal
    # AutoCAD-correct name (font_file); this only steers *this app's own* preview.
    fallback_families: Tuple[str, ...] = ()


FONT_CATALOG: List[FontSpec] = [
    FontSpec(
        "romans", "Roman Simplex (romans.shx)", "romans.shx", "technical",
        ("Consolas", "Hack", "Liberation Mono", "Courier New", "monospace"),
    ),
    FontSpec(
        "isocp", "ISO CP (isocp.shx)", "isocp.shx", "technical",
        ("Trebuchet MS", "Tahoma", "Verdana", "Nimbus Sans Narrow", "Cantarell", "sans-serif"),
    ),
    FontSpec(
        "simplex", "Simplex (simplex.shx)", "simplex.shx", "technical",
        ("Century Gothic", "Candara", "URW Gothic", "Comfortaa", "sans-serif"),
    ),
    FontSpec(
        "txt", "Standard (txt.shx)", "txt.shx", "technical",
        ("Courier New", "Nimbus Mono PS", "Consolas", "monospace"),
    ),
    FontSpec(
        "complex", "Complex (complex.shx)", "complex.shx", "technical",
        ("Cambria", "Caladea", "Georgia", "Liberation Serif", "serif"),
    ),
    FontSpec(
        "arial", "Arial", "arial.ttf", "standard",
        ("Arial", "Liberation Sans", "Helvetica", "Nimbus Sans", "DejaVu Sans", "sans-serif"),
    ),
    FontSpec(
        "times", "Times New Roman", "times.ttf", "standard",
        ("Times New Roman", "Liberation Serif", "Nimbus Roman", "DejaVu Serif", "serif"),
    ),
    FontSpec(
        "calibri", "Calibri", "calibri.ttf", "standard",
        ("Calibri", "Carlito", "Candara", "DejaVu Sans", "sans-serif"),
    ),
]

DEFAULT_FONT_ID = "calibri"

_BY_ID: Dict[str, FontSpec] = {spec.id: spec for spec in FONT_CATALOG}

ITALIC_OBLIQUE_ANGLE = 15.0
_ITALIC_STYLE_SUFFIX = "_ITALIC"

# Real Windows/AutoCAD italic TTF filenames - genuinely different font files (not just a
# style flag), which is required for ezdxf's own text renderer to draw them differently: its
# drawing add-on ignores the STYLE table's oblique angle entirely for plain TEXT entities
# (only honoured for MTEXT), so an italic style that keeps the same "font" attribute as its
# upright twin renders pixel-identical in this app's preview and in PDF export.
_STANDARD_ITALIC_FILES: Dict[str, str] = {
    "arial": "ariali.ttf",
    "times": "timesi.ttf",
    "calibri": "calibrii.ttf",
}
# Real AutoCAD-bundled single-stroke shape fonts, other than each font's own upright name -
# used only as a distinct internal lookup key per technical font (see ensure_text_style), so
# two different technical fonts don't collide onto the exact same italic substitute above.
_TECHNICAL_ITALIC_FILES: Dict[str, str] = {
    "romans": "italic.shx",
    "complex": "italic.shx",
    "isocp": "gothicg.shx",
    "simplex": "scripts.shx",
    "txt": "scriptc.shx",
}
# Tried only if a font's own fallback_families has no genuinely italic/oblique cut installed.
_UNIVERSAL_ITALIC_FALLBACK_FAMILIES: Tuple[str, ...] = (
    "Open Sans", "Noto Sans", "Liberation Sans", "DejaVu Sans",
)


def dxf_font_file(font_id: str, italic: bool) -> str:
    spec = font_spec(font_id)
    if not italic:
        return spec.font_file
    if spec.category == "standard":
        return _STANDARD_ITALIC_FILES.get(spec.id, spec.font_file)
    return _TECHNICAL_ITALIC_FILES.get(spec.id, "italic.shx")


@dataclass(frozen=True)
class LineweightPreset:
    id: str
    mm: Optional[float]


LINEWEIGHT_PRESETS: List[LineweightPreset] = [
    LineweightPreset("auto", None),
    LineweightPreset("thin", 0.13),
    LineweightPreset("normal", 0.18),
    LineweightPreset("bold", 0.25),
    LineweightPreset("extra_bold", 0.35),
]

_LINEWEIGHT_BY_ID: Dict[str, LineweightPreset] = {p.id: p for p in LINEWEIGHT_PRESETS}
DEFAULT_LINEWEIGHT_PRESET_ID = "auto"


def lineweight_preset(preset_id: str) -> LineweightPreset:
    return _LINEWEIGHT_BY_ID.get(preset_id, _LINEWEIGHT_BY_ID[DEFAULT_LINEWEIGHT_PRESET_ID])


def lineweight_preset_for_mm(mm: Optional[float]) -> LineweightPreset:
    for preset in LINEWEIGHT_PRESETS:
        if preset.mm == mm:
            return preset
    return _LINEWEIGHT_BY_ID[DEFAULT_LINEWEIGHT_PRESET_ID]


def font_spec(font_id: str) -> FontSpec:
    return _BY_ID.get(font_id, _BY_ID[DEFAULT_FONT_ID])


def text_style_name(font_id: str, italic: bool) -> str:
    spec = font_spec(font_id)
    return spec.id.upper() + (_ITALIC_STYLE_SUFFIX if italic else "")


def font_id_from_style_name(style_name: str) -> str:
    if not style_name:
        return DEFAULT_FONT_ID
    upper = style_name.upper()
    base = upper[: -len(_ITALIC_STYLE_SUFFIX)] if upper.endswith(_ITALIC_STYLE_SUFFIX) else upper
    return font_spec(base.lower()).id


def is_italic_style_name(style_name: str) -> bool:
    return style_name.upper().endswith(_ITALIC_STYLE_SUFFIX)


def _rendered_lookup_name(font_file: str) -> str:
    if ezdxf_fonts.is_shx_font_name(font_file):
        return ezdxf_fonts.map_shx_to_ttf(font_file)
    return font_file


_fallbacks_installed: Set[Tuple[str, bool]] = set()


def _best_italic_match(families: Tuple[str, ...]) -> Optional[ezdxf_fonts.FontFace]:
    for family in families:
        face = ezdxf_fonts.find_best_match(family=family, style="Italic")
        if face is not None and (face.is_italic or face.is_oblique):
            return face
    return None


def _best_upright_match(families: Tuple[str, ...]) -> Optional[ezdxf_fonts.FontFace]:
    for family in families:
        face = ezdxf_fonts.find_best_match(family=family, style="Regular")
        if face is not None:
            return face
    return None


def ensure_font_renders_distinctly(font_id: str, italic: bool = False) -> None:
    key = (font_id, italic)
    if key in _fallbacks_installed:
        return
    _fallbacks_installed.add(key)
    spec = font_spec(font_id)
    if not spec.fallback_families:
        return
    lookup_name = _rendered_lookup_name(dxf_font_file(font_id, italic))
    manager = ezdxf_fonts.font_manager
    if manager.has_font(lookup_name):
        return
    if not italic:
        face = _best_upright_match(spec.fallback_families)
    else:
        face = _best_italic_match(spec.fallback_families) or _best_italic_match(_UNIVERSAL_ITALIC_FALLBACK_FAMILIES)
        if face is None:
            face = _best_upright_match(spec.fallback_families)
    if face is not None:
        manager.add_synonyms({face.filename: lookup_name}, reverse=False)
