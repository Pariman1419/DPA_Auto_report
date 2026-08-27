"""
Unit tests for backend/scripts/purge_account_observability.py and the
rollup_daily_latency half-open date predicate in
backend/services/telemetry_service.py.

All DB access is mocked via the mock_db fixture from tests/conftest.py --
these tests assert on the SQL/params passed to cur.execute(), not against a
real database.
"""
from datetime import date

import pytest


pytestmark = pytest.mark.unit


def _executed_sql(cursor):
    """Concatenate all SQL strings passed to cur.execute() calls, for substring checks."""
    return "\n".join(call.args[0] for call in cursor.execute.call_args_list if call.args)


@pytest.mark.unit
def test_purge_request_telemetry_uses_90_day_half_open_cutoff(mock_db):
    conn, cursor = mock_db
    cursor.rowcount = 0

    from scripts.purge_account_observability import purge

    purge()

    sql = _executed_sql(cursor)
    assert "request_telemetry" in sql
    assert "90 days" in sql
    assert "occurred_at <" in sql
    assert "DATE(occurred_at)" not in sql


@pytest.mark.unit
def test_purge_audit_sessions_rollups_use_1_year_half_open_cutoff(mock_db):
    conn, cursor = mock_db
    cursor.rowcount = 0

    from scripts.purge_account_observability import purge

    purge()

    sql = _executed_sql(cursor)
    assert "account_audit_logs" in sql
    assert "user_sessions" in sql
    assert "endpoint_latency_daily" in sql
    assert sql.count("1 year") >= 3
    # column names must match each table's actual timestamp column
    assert "occurred_at" in sql  # account_audit_logs
    assert "started_at" in sql   # user_sessions
    assert "created_at" in sql   # endpoint_latency_daily


@pytest.mark.unit
def test_purge_returns_summary_counts_per_table(mock_db):
    conn, cursor = mock_db
    cursor.rowcount = 3

    from scripts.purge_account_observability import purge

    result = purge()

    assert isinstance(result, dict)
    assert "request_telemetry" in result
    assert result["request_telemetry"] == 3


@pytest.mark.unit
def test_rollup_daily_latency_uses_half_open_day_predicate(mock_db):
    conn, cursor = mock_db
    cursor.fetchall.return_value = []

    from services.telemetry_service import rollup_daily_latency

    rollup_daily_latency(target_date=date(2026, 8, 26))

    sql = _executed_sql(cursor)
    assert "occurred_at >=" in sql
    assert "occurred_at <" in sql
    assert "DATE(occurred_at)" not in sql
    assert "percentile_cont(0.95)" in sql.lower() or "percentile_cont(0.95)" in sql


@pytest.mark.unit
def test_rollup_daily_latency_upserts_on_route_day_conflict(mock_db):
    conn, cursor = mock_db
    cursor.fetchall.return_value = [
        {
            "route": "/api/stats",
            "request_count": 5,
            "error_count": 1,
            "avg_latency_ms": 12.5,
            "p95_latency_ms": 40.0,
            "max_latency_ms": 50,
        }
    ]

    from services.telemetry_service import rollup_daily_latency

    rollup_daily_latency(target_date=date(2026, 8, 26))

    sql = _executed_sql(cursor)
    assert "ON CONFLICT (route, day)" in sql
    assert "endpoint_latency_daily" in sql
