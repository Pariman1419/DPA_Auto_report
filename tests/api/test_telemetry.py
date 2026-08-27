"""
Tests for request-telemetry recording wired into request_log_middleware
(backend/main.py) and backed by services/telemetry_service.py.

These tests patch services.telemetry_service.record_request_telemetry
directly (the same "assert on call args" pattern used for login's
side-effect writes in tests/api/test_auth.py) rather than asserting on raw
DB rows, since the middleware calls that function and its own persistence
contract is covered separately in tests/unit/test_retention.py-adjacent
unit tests for telemetry_service itself.
"""
from unittest.mock import patch

import pytest
from fastapi import APIRouter


# ── Test-only route that always raises an unhandled exception ───────────────
# Registered once (module-scoped, autouse) on the shared session-scoped `app`
# fixture so PH-08 has something to hit that reaches request_log_middleware's
# except branch -- no production route deliberately raises an unhandled
# exception, so we need a dedicated one. The path is namespaced/unique enough
# to never collide with a real route or another test.
@pytest.fixture(scope="module", autouse=True)
def _raising_route(app):
    router = APIRouter()

    @router.get("/api/__test__/boom")
    def boom():
        raise RuntimeError("boom - unhandled test exception")

    app.include_router(router)
    yield
    app.router.routes = [
        r for r in app.router.routes if getattr(r, "path", None) != "/api/__test__/boom"
    ]


@pytest.mark.api
def test_protected_request_records_templated_route_status_duration_actor(client, admin_headers, mock_db):
    """
    A request to a route with a path param (mirrors /product-request/{pr_number})
    must be recorded with the TEMPLATED route, not the raw URL -- and with the
    actor's user id decoded from the JWT.
    """
    with patch("services.telemetry_service.record_request_telemetry") as mock_record:
        resp = client.get("/api/stats", headers=admin_headers)
        assert resp.status_code == 200

    assert mock_record.called
    _, kwargs = mock_record.call_args
    assert kwargs["route"] == "/api/stats"
    assert kwargs["method"] == "GET"
    assert kwargs["status_code"] == 200
    assert isinstance(kwargs["duration_ms"], (int, float))
    assert kwargs["duration_ms"] >= 0
    assert kwargs["user_id"] == "admin"


@pytest.mark.api
def test_templated_route_used_for_path_param_routes(client, admin_headers, mock_db):
    """
    A request against a path-parameterized route (/api/product-request/{pr_number}/lots)
    must record the TEMPLATE, e.g. '/api/product-request/{pr_number}/lots', not the
    concrete raw path '/api/product-request/PR123/lots' -- keeps cardinality low.
    """
    with patch("services.telemetry_service.record_request_telemetry") as mock_record:
        client.get("/api/product-request/PR123/lots", headers=admin_headers)

    assert mock_record.called
    _, kwargs = mock_record.call_args
    assert kwargs["route"] == "/api/product-request/{pr_number}/lots"
    assert "PR123" not in kwargs["route"]


@pytest.mark.api
def test_health_check_records_nothing(client):
    with patch("services.telemetry_service.record_request_telemetry") as mock_record:
        resp = client.get("/health")
        assert resp.status_code == 200

    mock_record.assert_not_called()


@pytest.mark.api
def test_unauthenticated_request_records_actor_as_none(client, mock_db):
    with patch("services.telemetry_service.record_request_telemetry") as mock_record:
        client.get("/api/stats")  # no auth headers -> 401

    assert mock_record.called
    _, kwargs = mock_record.call_args
    assert kwargs["user_id"] is None
    assert kwargs["status_code"] == 401


@pytest.mark.api
def test_telemetry_write_failure_does_not_change_response(client, admin_headers, mock_db):
    """
    record_request_telemetry's own contract is fail-open: a DB failure while
    writing telemetry must be swallowed INSIDE record_request_telemetry
    (per its own try/except) so it never propagates to the middleware, which
    calls it plainly with no try/except of its own. Simulate the failure at
    the DB layer -- not by mocking record_request_telemetry itself -- so the
    function's own fail-open behavior is what's under test.
    """
    with patch("services.telemetry_service.DBConnector") as mock_dbc:
        # Only telemetry_service's own module-level DBConnector reference is
        # replaced here -- product_request_service's reference (used by the
        # /api/stats endpoint itself, via the mock_db fixture) is untouched.
        mock_dbc.get_dpa_connection.side_effect = RuntimeError("db exploded")
        resp = client.get("/api/stats", headers=admin_headers)

    assert resp.status_code == 200


@pytest.mark.api
def test_reset_token_is_not_written_to_request_logs_or_telemetry(client, mock_db):
    """The reset secret must never escape into middleware observability."""
    raw_token = "secret-reset-token"
    with patch("services.telemetry_service.record_request_telemetry") as mock_record, \
         patch("main.log.info") as mock_log:
        client.post(f"/api/auth/reset-password/{raw_token}", json={"password": "NewPassw0rd!"})

    _, telemetry = mock_record.call_args
    assert raw_token not in telemetry["route"]
    assert all(raw_token not in str(call) for call in mock_log.call_args_list)


# ── PH-08: unhandled exceptions must not swallow logging/telemetry ─────────
@pytest.mark.api
def test_unhandled_exception_returns_sanitized_500_with_request_id(client, mock_db):
    """
    A route that raises an unhandled exception must still yield a 500
    response containing the request id (not the raw exception message/
    traceback), and telemetry must be recorded once with status 500 and the
    templated route.
    """
    with patch("services.telemetry_service.record_request_telemetry") as mock_record:
        resp = client.get("/api/__test__/boom")

    assert resp.status_code == 500
    body = resp.json()
    assert "boom" not in str(body).lower()
    # Some request-id-bearing field must be present in the sanitized body.
    request_id_value = body.get("request_id") or body.get("requestId")
    assert request_id_value, f"expected a request id in error body, got {body}"

    assert mock_record.call_count == 1
    _, kwargs = mock_record.call_args
    assert kwargs["route"] == "/api/__test__/boom"
    assert kwargs["method"] == "GET"
    assert kwargs["status_code"] == 500
    assert isinstance(kwargs["duration_ms"], (int, float))
    assert kwargs["duration_ms"] >= 0


# ── PH-09: the reset-password path must stay redacted through the exception
#    path too, not just the success path. ───────────────────────────────────
@pytest.mark.api
def test_unhandled_exception_on_reset_password_keeps_token_redacted(client, mock_db):
    raw_token = "raw-secret"
    with patch("services.telemetry_service.record_request_telemetry") as mock_record, \
         patch("main.log.exception") as mock_log_exc, \
         patch("routers.auth.DBConnector.get_dpa_connection", side_effect=RuntimeError("db exploded")):
        resp = client.post(
            f"/api/auth/reset-password/{raw_token}",
            json={"password": "NewPassw0rd!"},
        )

    assert resp.status_code == 500
    assert raw_token not in resp.text

    assert mock_record.call_count == 1
    _, kwargs = mock_record.call_args
    assert kwargs["route"] == "/api/auth/reset-password/{token}"
    assert kwargs["status_code"] == 500
    assert raw_token not in kwargs["route"]

    assert mock_log_exc.called
    logged = " ".join(str(call) for call in mock_log_exc.call_args_list)
    assert raw_token not in logged
