from __future__ import annotations

import pytest

import ui.i18n


@pytest.fixture(autouse=True)
def english_ui(monkeypatch):
    monkeypatch.setattr(ui.i18n, "_current_language", "en")
