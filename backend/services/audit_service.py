"""
Audit Service
Writes privileged account-administration actions to the `account_audit_logs`
table and mirrors a sanitized copy to a daily JSONL file for offline review.

Never persist credentials, password hashes, raw reset tokens, request bodies,
headers, or query strings here -- callers must only ever pass already-safe
before/after snapshots, and this module defensively strips a small set of
sensitive-looking keys as a last line of defense.
"""
import json
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from psycopg2.extras import Json

from services.db_connector import DBConnector
from logger import get_logger

log = get_logger("audit_service")

# Keys that must never be written to the DB row or the JSONL mirror, even if
# a caller accidentally includes them in before_state/after_state.
_SENSITIVE_KEY_MARKERS = (
    "password",
    "hash",
    "token",
    "secret",
    "authorization",
    "cookie",
)


@dataclass
class AuditEvent:
    actor_user_id: Optional[str]
    target_user_id: str
    action: str
    before_state: Optional[dict] = None
    after_state: Optional[dict] = None
    occurred_at: Optional[datetime] = None

    def __post_init__(self):
        if self.occurred_at is None:
            self.occurred_at = datetime.now(timezone.utc)


def _sanitize_state(state: Optional[dict]) -> Optional[dict]:
    """Strip any key that looks like it could hold a secret."""
    if not state:
        return state
    return {
        key: value
        for key, value in state.items()
        if not any(marker in key.lower() for marker in _SENSITIVE_KEY_MARKERS)
    }


def write_audit_event(event: AuditEvent):
    """
    Insert one row into account_audit_logs, then mirror a sanitized copy to
    the JSONL log. The JSONL mirror is fail-open: if it raises, the DB write
    that already happened is NOT undone and no exception propagates.
    """
    before = _sanitize_state(event.before_state)
    after = _sanitize_state(event.after_state)

    conn = DBConnector.get_dpa_connection()
    audit_id = None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO account_audit_logs
                    (actor_user_id, target_user_id, action, before_state, after_state, occurred_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    event.actor_user_id,
                    event.target_user_id,
                    event.action,
                    Json(before) if before is not None else None,
                    Json(after) if after is not None else None,
                    event.occurred_at,
                ),
            )
            row = cur.fetchone()
            audit_id = row[0] if row else None
        conn.commit()
    finally:
        DBConnector.release_dpa_connection(conn)

    mirror_event(event)
    return audit_id


def mirror_event(event: AuditEvent) -> None:
    """
    Append a sanitized JSON line for this event to
    {AUDIT_LOG_ROOT}/{YYYY-MM-DD}.jsonl.

    Fail-open: any error (permission, disk full, unreachable path) is logged
    as a warning and swallowed -- this must never raise and must never block
    or undo an already-successful audit DB write.
    """
    try:
        # Read env var per-call (not cached at import time) so tests and
        # runtime config changes both take effect immediately.
        audit_root = os.getenv("AUDIT_LOG_ROOT", r"D:\Auto_detect\logs\dpa-account-audit")
        root = pathlib.Path(audit_root)
        root.mkdir(parents=True, exist_ok=True)

        occurred_at = event.occurred_at or datetime.now(timezone.utc)
        file_path = root / f"{occurred_at:%Y-%m-%d}.jsonl"

        payload = {
            "actor_user_id": event.actor_user_id,
            "target_user_id": event.target_user_id,
            "action": event.action,
            "before_state": _sanitize_state(event.before_state),
            "after_state": _sanitize_state(event.after_state),
            "occurred_at": occurred_at.isoformat(),
        }

        with open(file_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, default=str))
            f.write("\n")
    except Exception as e:  # noqa: BLE001 - fail-open by design
        log.warning("Failed to mirror audit event to JSONL: %s", e)
