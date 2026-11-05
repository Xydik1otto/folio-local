# INSTALL.md: step-by-step for non-programmers, start.bat/start.sh, systemd unit.
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_install_md_exists_with_both_os_sections():
    md = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    assert "## Windows" in md and "## Linux" in md
    assert "shell:startup" in md                       # Windows autostart
    assert "systemctl --user enable --now folio-local" in md  # systemd
    assert "git pull" in md                            # updating section
    assert "folio.db" in md                            # where data lives


def test_windows_start_bat_is_sane():
    bat = (ROOT / "start.bat").read_text(encoding="utf-8")
    assert "python -m venv .venv" in bat
    assert "pip install -r requirements.txt" in bat
    assert "backend.main:app" in bat and "uvicorn" in bat


def test_start_sh_is_sane():
    sh = (ROOT / "start.sh").read_text(encoding="utf-8")
    assert "python3 -m venv .venv" in sh
    assert "uvicorn backend.main:app" in sh


def test_systemd_unit_exists_and_valid_shape():
    unit = (ROOT / "scripts" / "folio-local.service").read_text(encoding="utf-8")
    assert "[Unit]" in unit and "[Service]" in unit and "[Install]" in unit
    assert "WantedBy=default.target" in unit   # user unit, not system
    assert "uvicorn backend.main:app" in unit


def test_no_russian_in_install_docs():
    """Жорстке правило власника: російської локалізації не існує."""
    for name in ("INSTALL.md", "start.bat", "start.sh"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for ru in ("установка", "запускать", "сохранение", "настройка"):
            assert ru not in text.lower(), f"{name} contains Russian: {ru}"
