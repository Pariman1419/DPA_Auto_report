"""
Retention purge for account-administration/observability tables.

Deletes rows past their retention window using half-open, index-aligned
predicates (`col < now() - interval '...'`), never `DATE(col) < ...`, so the
deletes can use the existing occurred_at/started_at/created_at indexes
instead of forcing a full scan.

Retention windows (per the account-administration design spec):
  - request_telemetry:        90 days  (occurred_at)
  - account_audit_logs:       1 year   (occurred_at)
  - user_sessions:            1 year   (started_at)
  - endpoint_latency_daily:   1 year   (created_at)
  - password_reset_tokens:    7 days after expiry/use (bonus item, schema-
    driven -- not explicitly named in the Task 5 brief's own test-scenario
    list, but included since password_reset_tokens has a clear expiry/used_at
    lifecycle and the design spec's data-model table calls it out)

Never logs row contents -- only per-table row counts.

Run standalone:
    python -m backend.scripts.purge_account_observability
or, with backend/ on sys.path (as main.py itself is normally run):
    python scripts/purge_account_observability.py
"""
import os
import sys

# Allow running this file directly (python backend/scripts/purge_account_observability.py)
# as well as as a module, by making sure backend/ is on sys.path either way.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.dirname(_THIS_DIR)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from services.db_connector import DBConnector
from logger import get_logger

log = get_logger("purge_account_observability")


def purge() -> dict:
    """
    Delete rows past retention for each table and return a dict of
    {table_name: rows_deleted}. Runs each table's DELETE in its own
    statement on one connection/transaction, committed together.
    """
    results = {}

    conn = DBConnector.get_dpa_connection()
    if not conn:
        log.error("purge_account_observability: no DB connection available, aborting")
        return results
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM request_telemetry WHERE occurred_at < now() - interval '90 days'"
            )
            results["request_telemetry"] = cur.rowcount

            cur.execute(
                "DELETE FROM account_audit_logs WHERE occurred_at < now() - interval '1 year'"
            )
            results["account_audit_logs"] = cur.rowcount

            cur.execute(
                "DELETE FROM user_sessions WHERE started_at < now() - interval '1 year'"
            )
            results["user_sessions"] = cur.rowcount

            cur.execute(
                "DELETE FROM endpoint_latency_daily WHERE created_at < now() - interval '1 year'"
            )
            results["endpoint_latency_daily"] = cur.rowcount

            # Bonus item (schema-driven, not in the brief's own test-scenario
            # list): purge spent/expired password reset tokens 7 days after
            # they became unusable, per the design spec's data-model table.
            cur.execute(
                """
                DELETE FROM password_reset_tokens
                WHERE (used_at IS NOT NULL AND used_at < now() - interval '7 days')
                   OR (used_at IS NULL AND expires_at < now() - interval '7 days')
                """
            )
            results["password_reset_tokens"] = cur.rowcount
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        DBConnector.release_dpa_connection(conn)

    log.info("Retention purge complete: %s", results)
    return results


def main():
    purge()


if __name__ == "__main__":
    main()
