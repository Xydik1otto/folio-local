# Bilingual docs (README.uk + README.en), INSTALL.md, packaging metadata.
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_readme_en_exists_and_is_english():
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "Self-hosted investment portfolio tracker" in en
    assert "## Quick start" in en
    assert "## License" in en


def test_readme_en_links_ukrainian_original():
    en = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "[README.md](README.md)" in en
    uk = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Самохостинговий трекер інвестиційного портфеля" in uk


def test_no_russian_locale_anywhere():
    """Жорстке правило власника: російської локалізації НІКОЛИ не додавати."""
    for name in ("README.md", "README.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        # Cyrillic is fine (Ukrainian), but distinctive Russian-only words are not
        for ru_marker in ("регистрация", "портфельный", "данные", "поддержка"):
            assert ru_marker not in text, f"{name} contains Russian: {ru_marker}"
