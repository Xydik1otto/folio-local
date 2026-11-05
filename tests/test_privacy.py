# Privacy-first page «Облік без реєстрації»: /privacy + link from the app shell.
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_privacy_page_served():
    r = client.get("/privacy")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_privacy_page_content():
    html = client.get("/privacy").text
    assert "Облік без реєстрації" in html
    assert "Без реєстрації" in html
    # key factual claims the page makes must all be present
    for claim in ("SQLite", "Без телеметрії", "PWA", "Stooq"):
        assert claim in html


def test_privacy_page_has_no_tracker_scripts():
    html = client.get("/privacy").text
    # no third-party analytics scripts at all
    for tracker in ("googletagmanager", "google-analytics", "hotjar",
                    "yandex.ru/metrika", "facebook.net"):
        assert tracker not in html


def test_app_shell_links_privacy_page():
    html = client.get("/").text
    assert 'href="/privacy"' in html
