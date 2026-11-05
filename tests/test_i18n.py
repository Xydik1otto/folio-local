# i18n UA/EN switcher: JSON dictionaries, browser-language detect, choice saved.
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_dictionaries_exist_and_are_valid_json():
    for lang in ("uk", "en"):
        d = json.loads((STATIC / "i18n" / f"{lang}.json").read_text(encoding="utf-8"))
        assert d, lang


def test_dictionaries_have_the_same_keys():
    uk = json.loads((STATIC / "i18n" / "uk.json").read_text(encoding="utf-8"))
    en = json.loads((STATIC / "i18n" / "en.json").read_text(encoding="utf-8"))
    assert set(uk) == set(en), set(uk) ^ set(en)
    assert len(uk) >= 30  # covers headings, buttons, table headers, messages


def test_no_russian_locale_and_no_russian_strings():
    """Жорстке правило власника: російської локалізації НЕМАЄ і не буде."""
    files = list((STATIC / "i18n").glob("*.json"))
    assert sorted(f.name for f in files) == ["en.json", "uk.json"]
    for f in files:
        text = f.read_text(encoding="utf-8")
        for ru in ("регистрация", "настройки", "сохранить", "загрузить", "язык"):
            assert ru not in text, f"{f.name} contains Russian: {ru}"


def test_switcher_present_in_ui():
    html = client.get("/").text
    assert 'id="langSel"' in html
    assert 'value="uk"' in html and 'value="en"' in html
    assert "localStorage" in html          # choice persists
    assert "navigator.languages" in html   # browser-language detection
    assert "data-i18n" in html


def test_index_html_lang_is_uk_by_default():
    html = client.get("/").text
    assert '<html lang="uk">' in html
