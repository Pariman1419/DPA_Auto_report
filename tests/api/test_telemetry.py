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
