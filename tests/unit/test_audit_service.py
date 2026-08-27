"""
Unit tests for services/audit_service.py and services/account_admin_service.py.

Covers:
  - write_audit_event: parameterized INSERT into account_audit_logs
  - mirror_event: one JSON object per line, written under a temp AUDIT_LOG_ROOT
  - mirror_event fail-open: JSONL write failure never raises and never undoes
    the DB write already performed by write_audit_event
  - account_admin_service.list_accounts / change_status / create_reset_link /
    permanently_delete / activity / performance
  - permanently_delete requires a non-blank reason and a matching confirm id
  - reset tokens are only ever stored as a SHA-256 hash, never raw
"""
import hashlib
import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

from services.audit_service import AuditEvent, write_audit_event, mirror_event
from services import account_admin_service as svc


# ── AuditEvent / write_audit_event ──────────────────────────────────────────

def test_audit_event_defaults_occurred_at_when_not_given():
    event = AuditEvent(
        actor_user_id="admin",
        target_user_id="EMP001",
        action="disable",
    )
    assert event.occurred_at is not None


def test_write_audit_event_inserts_parameterized_row(mock_db):
    conn, cur = mock_db
    cur.fetchone.return_value = (1,)

    event = AuditEvent(
        actor_user_id="admin",
        target_user_id="EMP001",
        action="disable",
        before_state={"account_status": "active"},
        after_state={"account_status": "disabled"},
    )
    write_audit_event(event)

    assert cur.execute.called
    sql, params = cur.execute.call_args[0]
    assert "INSERT INTO account_audit_logs" in sql
    assert "%s" in sql
    # No f-string / string-formatted values in the SQL itself
    assert "admin" not in sql
    assert "EMP001" not in sql
    assert params[0] == "admin"
    assert params[1] == "EMP001"
    assert params[2] == "disable"
    assert conn.commit.called


def test_write_audit_event_calls_mirror_event(mock_db, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))
    conn, cur = mock_db
    cur.fetchone.return_value = (7,)

    event = AuditEvent(
        actor_user_id="admin",
        target_user_id="EMP002",
        action="approve",
    )
    write_audit_event(event)

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1


# ── mirror_event: JSONL format ──────────────────────────────────────────────

def test_mirror_event_writes_one_json_object_per_line(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))

    event1 = AuditEvent(actor_user_id="admin", target_user_id="EMP001", action="approve")
    event2 = AuditEvent(actor_user_id="admin", target_user_id="EMP002", action="disable")
    mirror_event(event1)
    mirror_event(event2)

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        obj = json.loads(line)
        assert obj["action"] in ("approve", "disable")


def test_mirror_event_creates_audit_root_if_missing(tmp_path, monkeypatch):
    missing_root = tmp_path / "nested" / "audit-root"
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(missing_root))

    event = AuditEvent(actor_user_id="admin", target_user_id="EMP001", action="approve")
    mirror_event(event)

    assert missing_root.exists()
    assert len(list(missing_root.glob("*.jsonl"))) == 1


def test_mirror_event_never_contains_sensitive_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))

    event = AuditEvent(
        actor_user_id="admin",
        target_user_id="EMP001",
        action="reset_password",
        before_state={"password_hash": "$2b$12$shouldnotappear", "full_name": "A"},
        after_state={"token": "raw-secret-token", "token_hash": "abc123"},
    )
    mirror_event(event)

    content = list(tmp_path.glob("*.jsonl"))[0].read_text(encoding="utf-8")
    assert "shouldnotappear" not in content
    assert "raw-secret-token" not in content


# ── mirror_event fail-open behaviour ─────────────────────────────────────────

def test_mirror_event_failure_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "mkdir", _boom)

    event = AuditEvent(actor_user_id="admin", target_user_id="EMP001", action="approve")
    # Must not raise.
    mirror_event(event)


def test_write_audit_event_succeeds_even_if_mirror_fails(mock_db, monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))
    conn, cur = mock_db
    cur.fetchone.return_value = (3,)

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(pathlib.Path, "mkdir", _boom)

    event = AuditEvent(actor_user_id="admin", target_user_id="EMP001", action="approve")
    # Should not raise, and the DB insert should still have happened.
    write_audit_event(event)

    assert cur.execute.called
    assert conn.commit.called


# ── account_admin_service.list_accounts ─────────────────────────────────────

def test_list_accounts_parameterizes_status_and_search(mock_db):
    conn, cur = mock_db
    cur.fetchall.return_value = []

    svc.list_accounts(status="active", search="alice", limit=10)

    sql, params = cur.execute.call_args[0]
    assert "%s" in sql
    assert "account_status = %s" in sql
    assert "'active'" not in sql
    assert "alice" not in sql
    assert "active" in params
    assert any("alice" in p for p in params if isinstance(p, str))


def test_list_accounts_returns_next_cursor_when_more_rows(mock_db):
    conn, cur = mock_db
    rows = [{"user_id": f"EMP{i:03d}"} for i in range(1, 4)]  # limit+1 = 3 for limit=2
    cur.fetchall.return_value = rows

    result = svc.list_accounts(limit=2)

    assert len(result["items"]) == 2
    assert result["next_cursor"] == "EMP002"


# ── account_admin_service.change_status ──────────────────────────────────────

def test_change_status_rejects_invalid_status(mock_db):
    with pytest.raises(ValueError):
        svc.change_status("admin", "EMP001", "not-a-real-status")


def test_change_status_syncs_is_active_and_writes_audit(mock_db, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))
    conn, cur = mock_db
    cur.fetchone.side_effect = [
        {"user_id": "EMP001", "account_status": "active", "is_active": True},  # SELECT before
        (5,),  # RETURNING id from write_audit_event
    ]

    svc.change_status("admin", "EMP001", "disabled")

    update_calls = [c for c in cur.execute.call_args_list if "UPDATE users" in c[0][0]]
    assert len(update_calls) == 1
    sql, params = update_calls[0][0]
    assert "disabled" in params
    assert False in params  # is_active synced to False


# ── account_admin_service.create_reset_link ──────────────────────────────────

def test_create_reset_link_stores_only_hash_and_returns_raw_url(mock_db, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))
    conn, cur = mock_db
    cur.fetchone.side_effect = [
        {"user_id": "EMP001"},  # user exists check
        (9,),                    # RETURNING id from write_audit_event
    ]

    url = svc.create_reset_link("admin", "EMP001")

    assert isinstance(url, str) and len(url) > 0
    raw_token = url.rsplit("/", 1)[-1]

    insert_calls = [c for c in cur.execute.call_args_list if "INSERT INTO password_reset_tokens" in c[0][0]]
    assert len(insert_calls) == 1
    _, params = insert_calls[0][0]
    stored_hash = params[1]
    assert stored_hash == hashlib.sha256(raw_token.encode()).hexdigest()
    assert stored_hash != raw_token


# ── account_admin_service.permanently_delete ─────────────────────────────────

def test_permanently_delete_requires_nonblank_reason(mock_db):
    with pytest.raises(ValueError):
        svc.permanently_delete("admin", "EMP001", confirm_user_id="EMP001", reason="")


def test_permanently_delete_requires_reason_not_whitespace(mock_db):
    with pytest.raises(ValueError):
        svc.permanently_delete("admin", "EMP001", confirm_user_id="EMP001", reason="   ")


def test_permanently_delete_requires_confirm_id_match(mock_db):
    with pytest.raises(ValueError):
        svc.permanently_delete(
            "admin", "EMP001", confirm_user_id="EMP999", reason="policy violation"
        )


def test_permanently_delete_writes_snapshot_before_delete(mock_db, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIT_LOG_ROOT", str(tmp_path))
    conn, cur = mock_db
    cur.fetchone.side_effect = [
        {
            "user_id": "EMP001",
            "full_name": "QA Engineer",
            "password_hash": "$2b$12$shouldneverbepersisted",
            "account_status": "disabled",
        },  # SELECT before delete
        (11,),  # RETURNING id from write_audit_event
    ]

    result = svc.permanently_delete(
        "admin", "EMP001", confirm_user_id="EMP001", reason="requested by employee"
    )

    assert result["deleted"] is True
    delete_calls = [c for c in cur.execute.call_args_list if "DELETE FROM users" in c[0][0]]
    assert len(delete_calls) == 1

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "shouldneverbepersisted" not in content


# ── account_admin_service.activity / performance ─────────────────────────────

def test_activity_queries_by_target_user_id(mock_db):
    conn, cur = mock_db
    cur.fetchall.return_value = []

    svc.activity("EMP001", limit=20)

    sql, params = cur.execute.call_args[0]
    assert "account_audit_logs" in sql
    assert "%s" in sql
    assert "EMP001" in params


def test_performance_queries_request_telemetry_for_user(mock_db):
    conn, cur = mock_db
    cur.fetchone.return_value = {
        "request_count": 10,
        "error_count": 1,
        "avg_duration_ms": 120.5,
        "max_duration_ms": 900,
    }

    result = svc.performance("EMP001")

    sql, params = cur.execute.call_args[0]
    assert "request_telemetry" in sql
    assert "EMP001" in params
    assert result["request_count"] == 10
