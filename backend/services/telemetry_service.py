"""
Telemetry Service
Records per-request usage/latency telemetry (request_telemetry) and rolls it
up into daily per-route aggregates (endpoint_latency_daily).

record_request_telemetry is called from backend/main.py's
request_log_middleware on every non-/health request. It is intentionally
best-effort observability, not an auth gate or a business-critical write --
any failure (DB unavailable, pool exhausted, etc.) is caught here and logged
as a warning; it must never propagate out and change the HTTP response the
client receives.

rollup_daily_latency is NOT wired into the request/response cycle -- it is
meant to be invoked by a scheduled job (out of scope for this task) once per
day to pre-aggregate request_telemetry into endpoint_latency_daily, which is
what services.account_admin_service.performance() (and any future dashboard)
reads from for cheap, index-aligned time-range queries.

Never store request bodies, query strings, or headers here -- request_telemetry
intentionally has no columns for them.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from psycopg2.extras import RealDictCursor

from services.db_connector import DBConnector
from logger import get_logger

log = get_logger("telemetry_service")


def record_request_telemetry(
    request_id=None,
    user_id: Optional[str] = None,
    route: str = "",
    method: Optional[str] = None,
    status_code: Optional[int] = None,
    duration_ms: Optional[float] = None,
) -> None:
    """
    Write one row to request_telemetry. Fail-open: any exception (DB
    unavailable, pool exhausted, bad params, etc.) is caught and logged as a
    warning here, never raised to the caller. request_telemetry has no
    request_id column (see migrations/050_account_administration.sql) --
    request_id is accepted only for log/trace correlation and is not
    persisted.
    """
    try:
        conn = DBConnector.get_dpa_connection()
        if not conn:
            log.warning("telemetry write skipped: no DB connection available")
            return
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO request_telemetry
                        (user_id, route, method, status_code, duration_ms)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, route, method, status_code, duration_ms),
                )
            conn.commit()
        finally:
            DBConnector.release_dpa_connection(conn)
    except Exception as e:
        log.warning("Failed to record request telemetry: %s", e)


def rollup_daily_latency(target_date: Optional[date] = None) -> int:
    """
    Aggregate one calendar day of request_telemetry into endpoint_latency_daily,
    grouped by route, upserting on the (route, day) unique constraint.

    Defaults to TODAY (not yesterday) when target_date is omitted. Rationale:
    this function has no scheduling opinion of its own -- the caller (a cron
    job, out of scope for this task) decides which day to roll up and when.
    Defaulting to "today" makes an ad-hoc/manual invocation (e.g. from a
    shell or an admin action) roll up the day someone is actually looking
    at, which is the more useful default for interactive/manual calls; a
    scheduled nightly job should explicitly pass yesterday's date rather
    than rely on this default.

    Uses a half-open, index-aligned predicate (occurred_at >= day_start AND
    occurred_at < day_start + 1) rather than DATE(occurred_at) = %s, so the
    query can use the (route, occurred_at DESC) index from Task 1.

    Returns the number of routes upserted.
    """
    if target_date is None:
        target_date = datetime.now(timezone.utc).date()

    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    conn = DBConnector.get_dpa_connection()
    if not conn:
        log.warning("rollup_daily_latency skipped: no DB connection available")
        return 0
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    route,
                    COUNT(*) AS request_count,
                    COUNT(*) FILTER (WHERE status_code >= 400) AS error_count,
                    AVG(duration_ms) AS avg_latency_ms,
                    percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms) AS p95_latency_ms,
                    MAX(duration_ms) AS max_latency_ms
                FROM request_telemetry
                WHERE occurred_at >= %s AND occurred_at < %s
                GROUP BY route
                """,
                (day_start, day_end),
            )
            rows = cur.fetchall()

            for row in rows:
                cur.execute(
                    """
                    INSERT INTO endpoint_latency_daily
                        (route, day, request_count, error_count, avg_latency_ms,
                         p95_latency_ms, max_latency_ms, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (route, day) DO UPDATE SET
                        request_count  = EXCLUDED.request_count,
                        error_count    = EXCLUDED.error_count,
                        avg_latency_ms = EXCLUDED.avg_latency_ms,
                        p95_latency_ms = EXCLUDED.p95_latency_ms,
                        max_latency_ms = EXCLUDED.max_latency_ms,
                        updated_at     = CURRENT_TIMESTAMP
                    """,
                    (
                        row["route"],
                        target_date,
                        row["request_count"],
                        row["error_count"],
                        row["avg_latency_ms"],
                        row["p95_latency_ms"],
                        row["max_latency_ms"],
                    ),
                )
        conn.commit()
        return len(rows)
    except Exception:
        conn.rollback()
        raise
    finally:
        DBConnector.release_dpa_connection(conn)
