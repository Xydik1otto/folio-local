# Mobile PWA: manifest + service worker + offline shell.
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)


def test_manifest_served_and_valid():
    r = client.get("/static/manifest.webmanifest")
    assert r.status_code == 200
    man = json.loads(r.content)
    assert man["name"] == "folio-local"
    assert man["start_url"] == "/"
    assert man["display"] == "standalone"
    assert man["icons"] and man["icons"][0]["src"] == "/static/favicon.svg"
    assert "application/manifest+json" in r.headers["content-type"]


def test_service_worker_served():
    r = client.get("/static/sw.js")
    assert r.status_code == 200
    assert "addEventListener" in r.text and "caches" in r.text  # worker JS sanity
    assert 'CACHE' in r.text


def test_service_worker_never_caches_api():
    sw = client.get("/static/sw.js").text
    assert 'url.pathname.startsWith("/api/")' in sw  # explicit API bypass


def test_index_links_manifest_and_registers_sw():
    r = client.get("/")
    assert r.status_code == 200
    html = r.text
    assert 'rel="manifest"' in html and "/static/manifest.webmanifest" in html
    assert "navigator.serviceWorker.register" in html
    assert 'name="theme-color"' in html
    assert 'name="viewport"' in html


def test_favicon_for_pwa_icon_exists():
    assert client.get("/static/favicon.svg").status_code == 200
