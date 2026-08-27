"""
Schema tests for the account-administration migration
(backend/migrations/050_account_administration.sql).

These tests spin up a disposable PostgreSQL container via Docker, apply
schema.sql followed by the migration TWICE, and assert that:
  * both applications succeed without error (idempotency)
  * the expected tables/columns/indexes exist afterwards

If Docker is unavailable, the test is skipped rather than failed so the
rest of the suite stays runnable on machines without Docker.
"""
import shutil
import subprocess
import time
import pathlib

import pytest

# NOTE: intentionally NOT a module-level `pytestmark` -- this file also holds
# the Task 4 API tests below (marked `api`), and a module-level pytestmark
# would force the `integration` marker onto every test in the file. The
# schema test itself is marked individually instead.

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
SCHEMA_SQL = REPO_ROOT / "schema.sql"
MIGRATION_SQL = REPO_ROOT / "backend" / "migrations" / "050_account_administration.sql"

CONTAINER_NAME = "dpa-schema-test"
TEST_PORT = 55432
TEST_DB = "DPA_TEST"
TEST_USER = "postgres"
TEST_PASSWORD = "postgres_test"


def _docker_available():
    return shutil.which("docker") is not None


@pytest.fixture(scope="module")
def pg_container():
    if not _docker_available():
        pytest.skip("Docker is not available in this environment")

    # Clean up any stale container from a previous failed run.
    subprocess.run(
        ["docker", "rm", "-f", CONTAINER_NAME],
        capture_output=True,
    )

    run_result = subprocess.run(
        [
            "docker", "run", "-d", "--name", CONTAINER_NAME,
            "-e", f"POSTGRES_PASSWORD={TEST_PASSWORD}",
            "-e", f"POSTGRES_DB={TEST_DB}",
            "-e", f"POSTGRES_USER={TEST_USER}",
            "-p", f"{TEST_PORT}:5432",
            "postgres:16",
        ],
        capture_output=True, text=True,
    )
    if run_result.returncode != 0:
        pytest.skip(f"Could not start disposable Postgres container: {run_result.stderr}")

    try:
        _wait_for_postgres()
        yield {
            "host": "localhost",
            "port": TEST_PORT,
            "dbname": TEST_DB,
            "user": TEST_USER,
            "password": TEST_PASSWORD,
        }
    finally:
        subprocess.run(["docker", "rm", "-f", CONTAINER_NAME], capture_output=True)


def _wait_for_postgres(timeout=60):
    import psycopg2
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            conn = psycopg2.connect(
                host="localhost", port=TEST_PORT, dbname=TEST_DB,
                user=TEST_USER, password=TEST_PASSWORD,
                connect_timeout=3,
            )
            conn.close()
            return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1)
    raise RuntimeError(f"Postgres container did not become ready in time: {last_err}")


def _run_sql_file(conn, path: pathlib.Path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


@pytest.mark.integration
def test_account_admin_schema(pg_container):
    import psycopg2

    conn = psycopg2.connect(**pg_container)
    try:
        # Apply base schema once, then the migration TWICE to prove idempotency.
        _run_sql_file(conn, SCHEMA_SQL)
        _run_sql_file(conn, MIGRATION_SQL)
        _run_sql_file(conn, MIGRATION_SQL)

        with conn.cursor() as cur:
            # --- users lifecycle/session columns -------------------------
            cur.execute("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'users'
            """)
            user_cols = {row[0]: row[1] for row in cur.fetchall()}
            assert "account_status" in user_cols
            assert "session_version" in user_cols

            # --- expected tables exist ------------------------------------
            cur.execute("""
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
            tables = {row[0] for row in cur.fetchall()}
            for expected in (
                "account_audit_logs",
                "user_sessions",
                "request_telemetry",
                "endpoint_latency_daily",
                "password_reset_tokens",
            ):
                assert expected in tables, f"missing table: {expected}"

            # --- timestamptz typing (never bare TIMESTAMP) ------------------
            cur.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns
                WHERE table_name IN (
                    'account_audit_logs', 'user_sessions', 'request_telemetry',
                    'endpoint_latency_daily', 'password_reset_tokens'
                )
                AND column_name ~ '_at$'
            """)
            for table_name, column_name, data_type in cur.fetchall():
                assert data_type == "timestamp with time zone", (
                    f"{table_name}.{column_name} is {data_type}, expected TIMESTAMPTZ"
                )

            # --- JSONB before/after fields on account_audit_logs -----------
            cur.execute("""
                SELECT column_name, data_type FROM information_schema.columns
                WHERE table_name = 'account_audit_logs'
            """)
            audit_cols = {row[0]: row[1] for row in cur.fetchall()}
            assert audit_cols.get("before_state") == "jsonb"
            assert audit_cols.get("after_state") == "jsonb"

            # --- password_reset_tokens stores only a hash, never raw token -
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'password_reset_tokens'
            """)
            reset_cols = {row[0] for row in cur.fetchall()}
            assert "token_hash" in reset_cols
            assert "token" not in reset_cols
            assert "raw_token" not in reset_cols

            # --- required indexes (checked per-table so an index on the
            # wrong table cannot incorrectly satisfy the assertion) ---------
            def _indexdefs_for(table_name):
                cur.execute(
                    "SELECT indexdef FROM pg_indexes "
                    "WHERE schemaname = 'public' AND tablename = %s",
                    (table_name,),
                )
                return " ".join(row[0] for row in cur.fetchall())

            audit_indexdefs = _indexdefs_for("account_audit_logs")
            assert "(target_user_id, occurred_at DESC)" in audit_indexdefs, \
                "account_audit_logs missing (target_user_id, occurred_at DESC) index"
            assert "(actor_user_id, occurred_at DESC)" in audit_indexdefs, \
                "account_audit_logs missing (actor_user_id, occurred_at DESC) index"

            session_indexdefs = _indexdefs_for("user_sessions")
            assert "(user_id, started_at DESC)" in session_indexdefs, \
                "user_sessions missing (user_id, started_at DESC) index"

            telemetry_indexdefs = _indexdefs_for("request_telemetry")
            assert "(user_id, occurred_at DESC)" in telemetry_indexdefs, \
                "request_telemetry missing (user_id, occurred_at DESC) index"
            assert "(route, occurred_at DESC)" in telemetry_indexdefs, \
                "request_telemetry missing (route, occurred_at DESC) index"
    finally:
        conn.close()


# ===========================================================================
# API tests for /api/admin/accounts/* (Task 4)
#
# These mock services.account_admin_service directly (patched on the
# routers.account_admin module, where the router does
# `from services import account_admin_service` and calls
# account_admin_service.<fn>(...)) rather than the DB layer -- the service
# functions' own DB behaviour is Task 2's concern; this file verifies the
# router's role gating, request/response shaping, error translation, and the
# self/last-admin guards that live in the router per Task 4's design.
# ===========================================================================
import pytest
from unittest.mock import patch

pytestmark_api = pytest.mark.api


NON_ADMIN_ROUTES = [
    ("get", "/api/admin/accounts"),
    ("post", "/api/admin/accounts/EMP999/approve"),
    ("post", "/api/admin/accounts/EMP999/disable"),
    ("post", "/api/admin/accounts/EMP999/restore"),
    ("post", "/api/admin/accounts/EMP999/reset-link"),
    ("delete", "/api/admin/accounts/EMP999"),
    ("get", "/api/admin/accounts/EMP999/activity"),
    ("get", "/api/admin/accounts/EMP999/performance"),
    ("get", "/api/admin/sessions"),
    ("get", "/api/admin/performance/daily"),
]


@pytest.mark.api
@pytest.mark.parametrize("method,path", NON_ADMIN_ROUTES)
@pytest.mark.parametrize("token_fixture", ["qa_token", "user_token"])
def test_admin_routes_forbidden_for_non_admin_roles(client, method, path, token_fixture, request):
    """Every /api/admin/* route rejects both 'user' and 'QA Engineer' roles
    with 403 -- only role == 'admin' may invoke these endpoints."""
    client.cookies.clear()
    token = request.getfixturevalue(token_fixture)
    headers = {"Authorization": f"Bearer {token}"}
    if method == "delete":
        response = client.request(
            "DELETE", path, headers=headers,
            json={"confirmUserId": "EMP999", "reason": "test"},
        )
    else:
        response = getattr(client, method)(path, headers=headers)
    assert response.status_code == 403


@pytest.mark.api
def test_admin_routes_401_without_auth(client):
    """Unauthenticated requests are rejected before role checks even run."""
    client.cookies.clear()
    response = client.get("/api/admin/accounts")
    assert response.status_code == 401


# ── list_accounts ────────────────────────────────────────────────────────


def test_list_accounts_admin_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": [{"user_id": "EMP001", "role": "user"}], "next_cursor": None}
    with patch("routers.account_admin.account_admin_service.list_accounts", return_value=fake_result) as mock_list:
        response = client.get(
            "/api/admin/accounts?status=active&search=emp&limit=25",
            headers=admin_headers,
        )
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_list.assert_called_once_with(status="active", search="emp", cursor=None, limit=25)
    assert "resetUrl" not in response.text


def test_list_accounts_limit_over_100_rejected(client, admin_headers):
    client.cookies.clear()
    response = client.get("/api/admin/accounts?limit=101", headers=admin_headers)
    assert response.status_code == 422


# ── approve ──────────────────────────────────────────────────────────────


def test_approve_account_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"user_id": "EMP999", "account_status": "active", "is_active": True}
    with patch("routers.account_admin.account_admin_service.change_status", return_value=fake_result) as mock_cs:
        response = client.post("/api/admin/accounts/EMP999/approve", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_cs.assert_called_once_with("admin", "EMP999", "active")


def test_approve_account_not_found_returns_404(client, admin_headers):
    client.cookies.clear()
    with patch(
        "routers.account_admin.account_admin_service.change_status",
        side_effect=ValueError("user not found: GHOST"),
    ):
        response = client.post("/api/admin/accounts/GHOST/approve", headers=admin_headers)
    assert response.status_code == 404


# ── disable ──────────────────────────────────────────────────────────────


def test_disable_account_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"user_id": "EMP999", "account_status": "disabled", "is_active": False}
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "EMP999", "role": "user", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.change_status", return_value=fake_result) as mock_cs:
        response = client.post("/api/admin/accounts/EMP999/disable", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_cs.assert_called_once_with("admin", "EMP999", "disabled")


def test_disable_self_returns_409(client, admin_headers):
    """Self-disable is rejected before any service call -- would lock the
    admin out of their own account."""
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.get_account") as mock_get, \
         patch("routers.account_admin.account_admin_service.change_status") as mock_cs:
        response = client.post("/api/admin/accounts/admin/disable", headers=admin_headers)
    assert response.status_code == 409
    mock_get.assert_not_called()
    mock_cs.assert_not_called()


def test_disable_last_active_admin_returns_409(client, admin_headers):
    """Disabling the only active admin (not self) is rejected."""
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "OTHERADMIN", "role": "admin", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.count_active_admins", return_value=1), \
         patch("routers.account_admin.account_admin_service.change_status") as mock_cs:
        response = client.post("/api/admin/accounts/OTHERADMIN/disable", headers=admin_headers)
    assert response.status_code == 409
    mock_cs.assert_not_called()


def test_disable_admin_when_multiple_active_admins_succeeds(client, admin_headers):
    """Disabling an admin is fine when there are other active admins left."""
    client.cookies.clear()
    fake_result = {"user_id": "OTHERADMIN", "account_status": "disabled", "is_active": False}
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "OTHERADMIN", "role": "admin", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.count_active_admins", return_value=2), \
         patch("routers.account_admin.account_admin_service.change_status", return_value=fake_result) as mock_cs:
        response = client.post("/api/admin/accounts/OTHERADMIN/disable", headers=admin_headers)
    assert response.status_code == 200
    mock_cs.assert_called_once_with("admin", "OTHERADMIN", "disabled")


# ── restore ──────────────────────────────────────────────────────────────


def test_restore_account_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"user_id": "EMP999", "account_status": "active", "is_active": True}
    with patch("routers.account_admin.account_admin_service.change_status", return_value=fake_result) as mock_cs:
        response = client.post("/api/admin/accounts/EMP999/restore", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_cs.assert_called_once_with("admin", "EMP999", "active")


# ── reset-link ───────────────────────────────────────────────────────────


def test_reset_link_response_contains_raw_url_once(client, admin_headers):
    client.cookies.clear()
    fake_url = "http://localhost:9090/reset-password/some-raw-token-value"
    with patch("routers.account_admin.account_admin_service.create_reset_link", return_value=fake_url) as mock_rl:
        response = client.post("/api/admin/accounts/EMP999/reset-link", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == {"resetUrl": fake_url}
    mock_rl.assert_called_once_with("admin", "EMP999")


def test_reset_link_not_present_in_other_endpoint_responses(client, admin_headers):
    """The raw reset URL must never appear in list/activity/performance/
    approve/restore response bodies -- only /reset-link ever returns it."""
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.list_accounts",
               return_value={"items": [], "next_cursor": None}):
        r1 = client.get("/api/admin/accounts", headers=admin_headers)
    with patch("routers.account_admin.account_admin_service.activity",
               return_value={"items": [], "next_cursor": None}):
        r2 = client.get("/api/admin/accounts/EMP999/activity", headers=admin_headers)
    with patch("routers.account_admin.account_admin_service.performance",
               return_value={"request_count": 0, "error_count": 0, "avg_duration_ms": None, "max_duration_ms": None}):
        r3 = client.get("/api/admin/accounts/EMP999/performance", headers=admin_headers)
    with patch("routers.account_admin.account_admin_service.change_status",
               return_value={"user_id": "EMP999", "account_status": "active", "is_active": True}):
        r4 = client.post("/api/admin/accounts/EMP999/approve", headers=admin_headers)

    for r in (r1, r2, r3, r4):
        assert "resetUrl" not in r.text
        assert "reset-password" not in r.text


# ── permanent delete ─────────────────────────────────────────────────────


def test_delete_account_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"user_id": "EMP999", "deleted": True}
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "EMP999", "role": "user", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.permanently_delete", return_value=fake_result) as mock_pd:
        response = client.request(
            "DELETE",
            "/api/admin/accounts/EMP999",
            headers=admin_headers,
            json={"confirmUserId": "EMP999", "reason": "requested by user"},
        )
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_pd.assert_called_once_with("admin", "EMP999", "EMP999", "requested by user")


def test_delete_account_missing_body_returns_422(client, admin_headers):
    client.cookies.clear()
    response = client.request("DELETE", "/api/admin/accounts/EMP999", headers=admin_headers)
    assert response.status_code == 422


def test_delete_account_malformed_body_returns_422(client, admin_headers):
    client.cookies.clear()
    response = client.request(
        "DELETE",
        "/api/admin/accounts/EMP999",
        headers=admin_headers,
        json={"reason": "missing confirmUserId field"},
    )
    assert response.status_code == 422


def test_delete_account_service_value_error_returns_400(client, admin_headers):
    """confirmUserId mismatch / blank reason bubble up from the service as
    ValueError and are translated to 400."""
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "EMP999", "role": "user", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.permanently_delete",
               side_effect=ValueError("confirmUserId does not match the target account")):
        response = client.request(
            "DELETE",
            "/api/admin/accounts/EMP999",
            headers=admin_headers,
            json={"confirmUserId": "WRONG", "reason": "test"},
        )
    assert response.status_code == 400


def test_delete_self_returns_409(client, admin_headers):
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.get_account") as mock_get, \
         patch("routers.account_admin.account_admin_service.permanently_delete") as mock_pd:
        response = client.request(
            "DELETE",
            "/api/admin/accounts/admin",
            headers=admin_headers,
            json={"confirmUserId": "admin", "reason": "test"},
        )
    assert response.status_code == 409
    mock_get.assert_not_called()
    mock_pd.assert_not_called()


def test_delete_last_active_admin_returns_409(client, admin_headers):
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.get_account",
               return_value={"user_id": "OTHERADMIN", "role": "admin", "account_status": "active"}), \
         patch("routers.account_admin.account_admin_service.count_active_admins", return_value=1), \
         patch("routers.account_admin.account_admin_service.permanently_delete") as mock_pd:
        response = client.request(
            "DELETE",
            "/api/admin/accounts/OTHERADMIN",
            headers=admin_headers,
            json={"confirmUserId": "OTHERADMIN", "reason": "test"},
        )
    assert response.status_code == 409
    mock_pd.assert_not_called()


# ── activity ─────────────────────────────────────────────────────────────


def test_account_activity_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": [{"action": "change_status"}], "next_cursor": None}
    with patch("routers.account_admin.account_admin_service.activity", return_value=fake_result) as mock_act:
        response = client.get(
            "/api/admin/accounts/EMP999/activity?limit=10&cursor=2024-01-01T00:00:00",
            headers=admin_headers,
        )
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_act.assert_called_once_with("EMP999", limit=10, cursor="2024-01-01T00:00:00")


def test_account_activity_limit_over_100_rejected(client, admin_headers):
    client.cookies.clear()
    response = client.get("/api/admin/accounts/EMP999/activity?limit=500", headers=admin_headers)
    assert response.status_code == 422


# ── performance ──────────────────────────────────────────────────────────


def test_account_performance_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {
        "request_count": 12,
        "error_count": 1,
        "avg_duration_ms": 123.4,
        "max_duration_ms": 500.0,
    }
    with patch("routers.account_admin.account_admin_service.performance", return_value=fake_result) as mock_perf:
        response = client.get(
            "/api/admin/accounts/EMP999/performance?start=2024-01-01T00:00:00&end=2024-02-01T00:00:00",
            headers=admin_headers,
        )
    assert response.status_code == 200
    assert response.json() == fake_result
    args, kwargs = mock_perf.call_args
    assert args[0] == "EMP999"
    assert kwargs["start"].year == 2024 and kwargs["start"].month == 1
    assert kwargs["end"].year == 2024 and kwargs["end"].month == 2


def test_account_performance_no_date_filters(client, admin_headers):
    client.cookies.clear()
    fake_result = {"request_count": 0, "error_count": 0, "avg_duration_ms": None, "max_duration_ms": None}
    with patch("routers.account_admin.account_admin_service.performance", return_value=fake_result) as mock_perf:
        response = client.get("/api/admin/accounts/EMP999/performance", headers=admin_headers)
    assert response.status_code == 200
    mock_perf.assert_called_once_with("EMP999", start=None, end=None)


# ── sessions (system-wide) ──────────────────────────────────────────────


def test_list_sessions_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": [{"user_id": "EMP999", "ip_address": "10.1.2.3"}], "next_cursor": None}
    with patch("routers.account_admin.account_admin_service.sessions", return_value=fake_result) as mock_sessions:
        response = client.get("/api/admin/sessions?limit=10&cursor=abc", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_sessions.assert_called_once_with(user_id=None, limit=10, cursor="abc")


def test_list_sessions_filtered_by_user(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": [], "next_cursor": None}
    with patch("routers.account_admin.account_admin_service.sessions", return_value=fake_result) as mock_sessions:
        response = client.get("/api/admin/sessions?user_id=EMP999", headers=admin_headers)
    assert response.status_code == 200
    mock_sessions.assert_called_once_with(user_id="EMP999", limit=50, cursor=None)


def test_list_sessions_limit_over_100_rejected(client, admin_headers):
    client.cookies.clear()
    response = client.get("/api/admin/sessions?limit=500", headers=admin_headers)
    assert response.status_code == 422


def test_list_sessions_invalid_cursor_rejected(client, admin_headers):
    client.cookies.clear()
    with patch("routers.account_admin.account_admin_service.sessions", side_effect=ValueError("invalid sessions cursor")):
        response = client.get("/api/admin/sessions?cursor=not-a-cursor", headers=admin_headers)
    assert response.status_code == 400


# ── performance/daily (system-wide) ─────────────────────────────────────


def test_daily_performance_success(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": [{"route": "/api/product-requests", "day": "2026-08-27", "request_count": 5}]}
    with patch("routers.account_admin.account_admin_service.daily_performance", return_value=fake_result) as mock_dp:
        response = client.get("/api/admin/performance/daily?days=7&route=/api/product-requests", headers=admin_headers)
    assert response.status_code == 200
    assert response.json() == fake_result
    mock_dp.assert_called_once_with(days=7, route="/api/product-requests")


def test_daily_performance_defaults(client, admin_headers):
    client.cookies.clear()
    fake_result = {"items": []}
    with patch("routers.account_admin.account_admin_service.daily_performance", return_value=fake_result) as mock_dp:
        response = client.get("/api/admin/performance/daily", headers=admin_headers)
    assert response.status_code == 200
    mock_dp.assert_called_once_with(days=30, route=None)


def test_daily_performance_days_over_365_rejected(client, admin_headers):
    client.cookies.clear()
    response = client.get("/api/admin/performance/daily?days=9999", headers=admin_headers)
    assert response.status_code == 422
