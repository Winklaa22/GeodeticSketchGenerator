from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from ui.app_identity import app_settings
from ui.global_settings import language as _stored_language
from ui.global_settings import set_language as _persist_language
from ui.i18n.en import TRANSLATIONS as _EN
from ui.i18n.pl import TRANSLATIONS as _PL

LANGUAGES: List[Tuple[str, str]] = [("en", "English"), ("pl", "Polski")]

_TABLES: Dict[str, Dict[str, str]] = {"en": _EN, "pl": _PL}

_current_language: str = ""


def current_language() -> str:
    global _current_language
    if not _current_language:
        stored = _stored_language(app_settings())
        _current_language = stored if stored in _TABLES else "en"
    return _current_language


def set_current_language(code: str) -> None:
    global _current_language
    _current_language = code if code in _TABLES else "en"
    _persist_language(app_settings(), _current_language)


def tr(key: str, **kwargs: object) -> str:
    table = _TABLES.get(current_language(), _EN)
    text = table.get(key)
    if text is None:
        text = _EN.get(key, key)
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, IndexError):
        return text


def tr_options(pairs: Sequence[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [(key, tr(translation_key)) for key, translation_key in pairs]
