# Single-user HTTP Basic auth: off by default, env-configured, /api/health exempt.
import base64

import pytest
from fastapi.testclient import TestClient

from backend import main


def _header(user: str, password: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


@pytest.fixture()
def client_no_auth(monkeypatch):
    monkeypatch.delenv(main.AUTH_ENV_USER, raising=False)
    monkeypatch.delenv(main.AUTH_ENV_PASSWORD, raising=False)
    return TestClient(main.app)


@pytest.fixture()
def client_with_auth(monkeypatch):
    monkeypatch.setenv(main.AUTH_ENV_USER, "alice")
    monkeypatch.setenv(main.AUTH_ENV_PASSWORD, "s3cret")
    return TestClient(main.app)


def test_auth_disabled_by_default(client_no_auth):
    assert main.auth_enabled() is False
    assert client_no_auth.get("/api/health").status_code == 200
    assert client_no_auth.get("/api/accounts").status_code == 200


def test_enabled_rejects_missing_and_wrong_credentials(client_with_auth):
    r = client_with_auth.get("/api/accounts")
    assert r.status_code == 401
    assert r.headers["www-authenticate"].startswith("Basic")

    r = client_with_auth.get("/api/accounts", headers=_header("alice", "wrong"))
    assert r.status_code == 401

    r = client_with_auth.get("/api/accounts", headers=_header("bob", "s3cret"))
    assert r.status_code == 401


def test_enabled_accepts_correct_credentials(client_with_auth, monkeypatch, tmp_path):
    monkeypatch.setenv("FOLIO_DB", str(tmp_path / "auth.db"))
    r = client_with_auth.get("/api/accounts", headers=_header("alice", "s3cret"))
    assert r.status_code == 200
    assert r.json() == []


def test_health_is_exempt(client_with_auth):
    # Health probe stays open so uptime monitors / reverse proxies work.
    assert client_with_auth.get("/api/health").status_code == 200


def test_static_pages_are_protected(client_with_auth):
    assert client_with_auth.get("/").status_code == 401
    assert client_with_auth.get("/", headers=_header("alice", "s3cret")).status_code == 200


def test_malformed_authorization_header_rejected(client_with_auth):
    assert client_with_auth.get(
        "/api/accounts", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client_with_auth.get(
        "/api/accounts", headers={"Authorization": "Basic !!!not-base64!!!"}).status_code == 401


def test_only_user_set_is_not_enough(monkeypatch):
    """Half-configured env must NOT silently disable auth-checks... nor enable
    partial auth: it stays disabled only when BOTH are missing."""
    monkeypatch.delenv(main.AUTH_ENV_PASSWORD, raising=False)
    monkeypatch.setenv(main.AUTH_ENV_USER, "alice")
    assert main.auth_enabled() is False  # incomplete config -> open local mode
