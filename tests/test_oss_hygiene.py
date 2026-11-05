# OSS hygiene: community files, no privacy leaks, .env ignored, no Russian.
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TRACKED_EXTS = {".py", ".md", ".html", ".js", ".toml", ".json", ".bat",
                ".sh", ".service", ".txt", ".cfg", ".yml", ".yaml", ".ini"}
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git", "dist",
             "build", "node_modules", "docs", "bin", "obj"}


def tracked_files():
    out = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TRACKED_EXTS:
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def test_community_files_exist():
    for name in ("CONTRIBUTING.md", "SECURITY.md",
                 ".github/ISSUE_TEMPLATE/bug_report.md",
                 ".github/ISSUE_TEMPLATE/feature_request.md"):
        assert (ROOT / name).is_file(), name


def test_contributing_and_security_content():
    contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "pytest" in contributing and "commit" in contributing.lower()
    assert "ніколи не додавати російську" in contributing.lower()
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Private vulnerability reporting" in security
    assert "NOT open a public issue" in security


def test_no_local_absolute_paths_or_secrets_in_tracked_files():
    r"""Репозиторій піде в опенсорс: жодних G:\, C:\Users, токенів, .env значень."""
    leaks = []
    for p in tracked_files():
        if p.name == "test_oss_hygiene.py":
            continue  # this file embeds the detection patterns themselves
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        if re.search(r"[A-Z]:\\Users\\|G:\\|G:/Projects|/Users/\w+/", text):
            leaks.append(f"{p.name}: absolute local path")
        if re.search(r"(api[_-]?key|secret|password)\s*[=:]\s*['\"][A-Za-z0-9]{8,}",
                     text, re.I):
            leaks.append(f"{p.name}: hardcoded credential")
    assert not leaks, leaks


def test_no_russian_localization_anywhere():
    """Жорстке правило власника: НІКОЛИ не додавати російську локалізацію."""
    ru_markers = ("регистрация", "настройка", "сохранить", "загрузить",
                  "пользователя", "установка", "разработки", "портфельный")
    offenders = []
    for p in tracked_files():
        if p.parent.name == "tests":
            continue  # negative-assertion tests legitimately embed RU markers
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue
        low = text.lower()
        for m in ru_markers:
            if m in low:
                offenders.append(f"{p.name}: {m}")
    assert not offenders, offenders


def test_gitignore_covers_env():
    gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert re.search(r"^\.env$", gi, re.M)
    assert re.search(r"^\.env\.\*", gi, re.M)
    assert re.search(r"^\*\.db", gi, re.M)   # local DB never committed


def test_readme_has_contributing_section_and_topics():
    for name in ("README.md", "README.en.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "## Contributing" in text
        assert "GitHub topics" in text
        assert "portfolio-tracker" in text and "self-hosted" in text
