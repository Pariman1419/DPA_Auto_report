"""
Tests for GET /health (backend/main.py).

Covers PH-01a/PH-01b/PH-01c from
docs/superpowers/plans/2026-08-27-production-hardening.md: /health stays
public and DB-independent (infrastructure liveness/readiness probe), but the
gitSha field (sourced from APP_GIT_SHA) is only included for authenticated
admins -- non-admin/anonymous callers get {"status": "ok"} with no gitSha,
without leaking any secret-shaped values (DB credentials, JWT secret,
tokens).
"""
import os

import pytest


@pytest.mark.api
def test_health_unauthenticated_has_no_git_sha(client, monkeypatch):
    """PH-01a: GET /health with no auth -> 200, status only, no gitSha."""
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "gitSha" not in body
    assert set(body.keys()) == {"status"}


@pytest.mark.api
def test_health_admin_sees_git_sha(client, admin_cookies, monkeypatch):
    """PH-01b: GET /health authenticated as admin -> 200, status + gitSha."""
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health", cookies=admin_cookies)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["gitSha"] == "abc123"


@pytest.mark.api
def test_health_non_admin_has_no_git_sha(client, auth_cookies, monkeypatch):
    """PH-01c: GET /health authenticated as non-admin -> 200, status only."""
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health", cookies=auth_cookies)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "gitSha" not in body
    assert set(body.keys()) == {"status"}


@pytest.mark.api
def test_health_exposes_no_secret_values(client, admin_cookies, monkeypatch):
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health", cookies=admin_cookies)

    text = resp.text.lower()

    secret_values = [
        os.environ.get("DB_PASSWORD", ""),
        os.environ.get("JWT_SECRET_KEY", ""),
        os.environ.get("DB_USER", ""),
        os.environ.get("DB_HOST", ""),
    ]
    for secret in secret_values:
        if secret:
            assert secret.lower() not in text

    allowed_keys = {"status", "gitSha"}
    assert set(resp.json().keys()) <= allowed_keys
