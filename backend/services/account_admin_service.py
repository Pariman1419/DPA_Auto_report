"""
Account Admin Service
Data-access functions backing the admin account-lifecycle features: listing
accounts, changing lifecycle status, issuing one-time password reset links,
permanently deleting accounts, and reading per-account activity/performance.

Every privileged mutation writes an audit trail via
services.audit_service.write_audit_event (DB row + JSONL mirror).

Self/last-admin protection and HTTP-level request validation (confirmUserId
body shape, etc.) are the router's job (Task 4) -- this module only refuses
to proceed without the minimum data it needs to act safely.
"""
import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from psycopg2.extras import RealDictCursor

from services.db_connector import DBConnector
from services.audit_service import AuditEvent, write_audit_event, mirror_event, _sanitize_state, _json_state
from logger import get_logger

log = get_logger("account_admin_service")

VALID_ACCOUNT_STATUSES = {"pending", "active", "disabled", "deleted"}
RESET_TOKEN_TTL_MINUTES = 30
MAX_PAGE_SIZE = 100


def _clamp_limit(limit: int, default: int = 50) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = default
    return min(max(limit, 1), MAX_PAGE_SIZE)


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------


def list_accounts(
    status: Optional[str] = None,
    search: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 50,
) -> dict:
    """Cursor-paginated account listing with optional status/search filters."""
    page_size = _clamp_limit(limit)

    clauses = []
    params: list = []
    if status:
        clauses.append("account_status = %s")
        params.append(status)
    if search:
        clauses.append("(full_name ILIKE %s OR user_id ILIKE %s OR email ILIKE %s)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if cursor:
        clauses.append("user_id > %s")
        params.append(cursor)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(page_size + 1)

    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT user_id, full_name, email, role, account_status,
                       is_active, session_version, created_at
                FROM users
                {where}
                ORDER BY user_id
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        DBConnector.release_dpa_connection(conn)

    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = rows[-1]["user_id"]

    return {"items": rows, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# change_status
# ---------------------------------------------------------------------------


def change_status(actor_user_id: Optional[str], target_user_id: str, new_status: str) -> dict:
    """
    Update users.account_status (and the synchronized legacy is_active flag)
    and write an audit trail entry with before/after snapshots.
    """
    if new_status not in VALID_ACCOUNT_STATUSES:
        raise ValueError(f"invalid account_status: {new_status!r}")

    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, account_status, is_active FROM users WHERE user_id = %s",
                (target_user_id,),
            )
            before = cur.fetchone()
            if not before:
                raise ValueError(f"user not found: {target_user_id}")

            is_active = new_status == "active"
            cur.execute(
                "UPDATE users SET account_status = %s, is_active = %s WHERE user_id = %s",
                (new_status, is_active, target_user_id),
            )
        conn.commit()
    finally:
        DBConnector.release_dpa_connection(conn)

    write_audit_event(
        AuditEvent(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action="change_status",
            before_state=dict(before),
            after_state={"account_status": new_status, "is_active": is_active},
        )
    )

    return {"user_id": target_user_id, "account_status": new_status, "is_active": is_active}


# ---------------------------------------------------------------------------
# create_reset_link
# ---------------------------------------------------------------------------


def create_reset_link(actor_user_id: Optional[str], target_user_id: str) -> str:
    """
    Create a one-time password reset token, persist only its SHA-256 hash,
    and return the raw reset URL. The raw token is never stored or logged --
    this is the only place it is ever visible.
    """
    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT user_id FROM users WHERE user_id = %s", (target_user_id,))
            row = cur.fetchone()
            if not row:
                raise ValueError(f"user not found: {target_user_id}")

            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

            cur.execute(
                """
                INSERT INTO password_reset_tokens (user_id, token_hash, expires_at)
                VALUES (%s, %s, %s)
                """,
                (target_user_id, token_hash, expires_at),
            )
        conn.commit()
    finally:
        DBConnector.release_dpa_connection(conn)

    # Read per-call (not module-load time) so config changes take effect
    # immediately and tests can override it.
    base_url = os.getenv("BASE_URL", "http://localhost:9090")
    reset_url = f"{base_url.rstrip('/')}/reset-password/{token}"

    write_audit_event(
        AuditEvent(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            action="create_reset_link",
            before_state=None,
            after_state={"expires_at": expires_at.isoformat()},
        )
    )

    return reset_url


# ---------------------------------------------------------------------------
# permanently_delete
# ---------------------------------------------------------------------------


def permanently_delete(
    actor_user_id: Optional[str],
    target_user_id: str,
    confirm_user_id: str,
    reason: str,
) -> dict:
    """
    Permanently remove a user account. Requires a non-blank reason and a
    confirm_user_id that matches the target -- the last line of defense
    before an irreversible delete (the HTTP-level confirmUserId body
    validation is the router's job).

    Writes an audit log entry with a before_state snapshot BEFORE deleting
    the row. The snapshot SELECT, the audit-row INSERT, and the DELETE all
    run on the same connection/transaction and are committed together, so
    the audit trail can never claim a deletion that didn't actually happen
    (or vice versa) -- if the DELETE fails, the audit INSERT rolls back with
    it. The JSONL mirror is written only after that transaction commits,
    consistent with write_audit_event's own fail-open ordering.
    """
    if not reason or not reason.strip():
        raise ValueError("reason is required to permanently delete an account")
    if not confirm_user_id or confirm_user_id != target_user_id:
        raise ValueError("confirmUserId does not match the target account")

    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE user_id = %s", (target_user_id,))
            before = cur.fetchone()
            if not before:
                raise ValueError(f"user not found: {target_user_id}")

            before_state = {k: v for k, v in dict(before).items() if k != "password_hash"}
            before_state["reason"] = reason.strip()

            event = AuditEvent(
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                action="permanently_delete",
                before_state=before_state,
                after_state=None,
            )
            sanitized_before = _sanitize_state(event.before_state)
            sanitized_after = _sanitize_state(event.after_state)

            cur.execute(
                """
                INSERT INTO account_audit_logs
                    (actor_user_id, target_user_id, action, before_state, after_state, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    event.actor_user_id,
                    event.target_user_id,
                    event.action,
                    _json_state(sanitized_before),
                    _json_state(sanitized_after),
                    event.occurred_at,
                ),
            )

            cur.execute("DELETE FROM users WHERE user_id = %s", (target_user_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        DBConnector.release_dpa_connection(conn)

    # The JSONL mirror is explicitly fail-open and has no transactional
    # coupling to the DB row -- write it after the transaction above has
    # already committed both the audit insert and the delete.
    mirror_event(event)

    return {"user_id": target_user_id, "deleted": True}


# ---------------------------------------------------------------------------
# count_active_admins / get_account
# ---------------------------------------------------------------------------


def count_active_admins() -> int:
    """
    Count currently-active accounts with role='admin'. Used by the router
    (Task 4) to decide whether a disable/delete action would drop the system
    to zero active admins.
    """
    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM users WHERE role = %s AND account_status = %s",
                ("admin", "active"),
            )
            row = cur.fetchone()
    finally:
        DBConnector.release_dpa_connection(conn)
    return row[0] if row else 0


def get_account(user_id: str) -> Optional[dict]:
    """
    Single-row lookup of an account's role/status, used by the router (Task 4)
    to decide self/last-admin guard checks before calling change_status /
    permanently_delete.
    """
    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, full_name, email, role, account_status, is_active "
                "FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
    finally:
        DBConnector.release_dpa_connection(conn)
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# activity
# ---------------------------------------------------------------------------


def activity(target_user_id: str, limit: int = 50, cursor: Optional[str] = None) -> dict:
    """Paged audit-log activity for a single account, newest first."""
    page_size = _clamp_limit(limit)

    clauses = ["target_user_id = %s"]
    params: list = [target_user_id]
    if cursor:
        clauses.append("occurred_at < %s")
        params.append(cursor)
    params.append(page_size + 1)

    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT id, actor_user_id, target_user_id, action,
                       before_state, after_state, occurred_at
                FROM account_audit_logs
                WHERE {' AND '.join(clauses)}
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    finally:
        DBConnector.release_dpa_connection(conn)

    next_cursor = None
    if len(rows) > page_size:
        rows = rows[:page_size]
        next_cursor = rows[-1]["occurred_at"]

    return {"items": rows, "next_cursor": next_cursor}


# ---------------------------------------------------------------------------
# performance
# ---------------------------------------------------------------------------


def performance(
    target_user_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> dict:
    """
    Time-bounded request-telemetry summary for a single account: request
    count, error count, average/max latency. Date bounds are half-open
    (start inclusive, end exclusive) to stay index-aligned with
    (user_id, occurred_at DESC).
    """
    clauses = ["user_id = %s"]
    params: list = [target_user_id]
    if start:
        clauses.append("occurred_at >= %s")
        params.append(start)
    if end:
        clauses.append("occurred_at < %s")
        params.append(end)

    conn = DBConnector.get_dpa_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                SELECT
                    COUNT(*) AS request_count,
                    COUNT(*) FILTER (WHERE status_code >= 400) AS error_count,
                    AVG(duration_ms) AS avg_duration_ms,
                    MAX(duration_ms) AS max_duration_ms
                FROM request_telemetry
                WHERE {' AND '.join(clauses)}
                """,
                params,
            )
            row = cur.fetchone()
    finally:
        DBConnector.release_dpa_connection(conn)

    if not row:
        return {
            "request_count": 0,
            "error_count": 0,
            "avg_duration_ms": None,
            "max_duration_ms": None,
        }
    return dict(row)
