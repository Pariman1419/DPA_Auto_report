"""
Tests for GET /health (backend/main.py).

Covers PH-01 from docs/superpowers/plans/2026-08-27-production-hardening.md:
health must expose the running build's commit SHA (APP_GIT_SHA) for
deployment verification, without leaking any secret-shaped values
(DB credentials, JWT secret, tokens).

/health is called by unauthenticated monitoring today (see
tests/api/test_telemetry.py::test_health_check_records_nothing, which hits
it with no auth headers) so this test does not add an auth requirement to
the endpoint itself -- only the gitSha field's presence is under test here.
"""
import os

import pytest


@pytest.mark.api
def test_health_reports_configured_git_sha(client, monkeypatch):
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["gitSha"] == "abc123"


@pytest.mark.api
def test_health_exposes_no_secret_values(client, monkeypatch):
    monkeypatch.setenv("APP_GIT_SHA", "abc123")
    resp = client.get("/health")

    body = resp.json()
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
    assert set(body.keys()) <= allowed_keys
