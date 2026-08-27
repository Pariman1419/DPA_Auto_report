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

pytestmark = pytest.mark.integration

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

            # --- required indexes -------------------------------------------
            cur.execute("""
                SELECT indexname, indexdef FROM pg_indexes
                WHERE schemaname = 'public'
            """)
            indexdefs = " ".join(row[1] for row in cur.fetchall())

            assert "target_user_id" in indexdefs and "occurred_at" in indexdefs
            assert "(user_id, occurred_at" in indexdefs.replace(" DESC", "") \
                or "(user_id, occurred_at DESC)" in indexdefs
            assert "(route, occurred_at" in indexdefs.replace(" DESC", "") \
                or "(route, occurred_at DESC)" in indexdefs
    finally:
        conn.close()
