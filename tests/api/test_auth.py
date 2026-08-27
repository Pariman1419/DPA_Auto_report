"""
API tests for /api/auth/* endpoints.
Uses FastAPI TestClient and a mocked DB connector.
"""
import hashlib

import pytest
from unittest.mock import MagicMock, patch
from itsdangerous import SignatureExpired, BadSignature

pytestmark = pytest.mark.api


# ── Login Tests ───────────────────────────────────────────────────────────────

def test_login_success(client, mock_db, sample_user):
    """Successful login sets httpOnly cookie and returns token response."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = sample_user  # Mock finding the active user

    with patch("routers.auth.verify_password", return_value=True):
        login_payload = {"userId": "EMP001", "password": "test1234"}
        response = client.post("/api/auth/login", json=login_payload)

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["userId"] == "EMP001"
    assert data["user"]["role"] == "QA Engineer"
    
    # Assert httpOnly cookie is set
    assert "dpa_token" in response.cookies
    select_calls = [
        call for call in cur.execute.call_args_list
        if "SELECT user_id, full_name, role, password_hash, session_version" in call[0][0]
    ]
    assert len(select_calls) == 1
    assert select_calls[0][0][0] == (
        "SELECT user_id, full_name, role, password_hash, session_version "
        "FROM users WHERE user_id = %s AND account_status = %s AND is_active = True"
    )
    assert select_calls[0][0][1] == ("EMP001", "active")

    # A user_sessions row is written on successful login, for session history
    session_insert_calls = [
        call for call in cur.execute.call_args_list
        if "INSERT INTO user_sessions" in call[0][0]
    ]
    assert len(session_insert_calls) == 1
    insert_params = session_insert_calls[0][0][1]
    assert insert_params[0] == "EMP001"
    assert insert_params[1] is not None  # ip_address
    assert insert_params[2] is not None  # user_agent
    assert insert_params[3] is not None  # expires_at

    # New tokens carry the user's current session_version as the `sv` claim
    from services.auth_service import decode_token
    payload = decode_token(data["access_token"])
    assert payload["sv"] == sample_user["session_version"]


def test_login_password_upgrade(client, mock_db, sample_user):
    """Login with valid credentials and plain-text password upgrades the hash to bcrypt."""
    client.cookies.clear()
    conn, cur = mock_db
    # Plain text hash
    plain_user = dict(sample_user)
    plain_user["password_hash"] = "test1234"
    cur.fetchone.return_value = plain_user

    # Mock verify_password to return True for plain text comparison in legacy support
    with patch("routers.auth.verify_password", return_value=True):
        login_payload = {"userId": "EMP001", "password": "test1234"}
        response = client.post("/api/auth/login", json=login_payload)

    assert response.status_code == 200
    # Assert UPDATE query was executed to upgrade the password hash to bcrypt
    update_calls = [
        call for call in cur.execute.call_args_list 
        if "UPDATE users SET password_hash" in call[0][0]
    ]
    assert len(update_calls) == 1
    assert update_calls[0][0][1][1] == "EMP001"

    # A user_sessions row is also written on this login path
    session_insert_calls = [
        call for call in cur.execute.call_args_list
        if "INSERT INTO user_sessions" in call[0][0]
    ]
    assert len(session_insert_calls) == 1
    assert session_insert_calls[0][0][1][0] == "EMP001"

    # One commit for the password upgrade, one for the session insert
    assert conn.commit.call_count == 2


def test_login_invalid_password(client, mock_db, sample_user):
    """Login fails when password does not match the stored hash."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = sample_user

    with patch("routers.auth.verify_password", return_value=False):
        login_payload = {"userId": "EMP001", "password": "wrong_password"}
        response = client.post("/api/auth/login", json=login_payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Employee ID or password"


def test_login_inactive_user(client, mock_db):
    """Login fails if user is inactive (no user record returned)."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = None  # User is either missing or inactive

    login_payload = {"userId": "EMP999", "password": "test1234"}
    response = client.post("/api/auth/login", json=login_payload)

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid Employee ID or password"


def test_login_db_unavailable(client, monkeypatch):
    """Login returns 503 if DB connector cannot establish a connection."""
    client.cookies.clear()
    from services import db_connector
    monkeypatch.setattr(db_connector.DBConnector, "get_dpa_connection",
                        staticmethod(lambda: None))

    login_payload = {"userId": "EMP001", "password": "test1234"}
    response = client.post("/api/auth/login", json=login_payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "Database unavailable"


# ── Registration Tests ────────────────────────────────────────────────────────

def test_register_success(client, mock_db):
    """Registration creates inactive account and triggers SMTP email (mocked)."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = None  # ID not already taken

    register_payload = {
        "userId": "EMP005",
        "fullName": "New Employee",
        "email": "emp005@company.com",  # Use .com domain to avoid pydantic .test validation error
        "password": "newpassword123"
    }
    
    with patch("routers.auth.send_approval_email") as mock_email:
        response = client.post("/api/auth/register", json=register_payload)
        
        assert response.status_code == 200, response.json()
        assert "Account created" in response.json()["message"]
        mock_email.assert_called_once_with("EMP005", "New Employee", "emp005@company.com")

    # Assert INSERT was done
    insert_calls = [
        call for call in cur.execute.call_args_list
        if "INSERT INTO users" in call[0][0]
    ]
    assert len(insert_calls) == 1
    # Check that user is inserted as is_active=False (hardcoded in SQL VALUES)
    assert "False" in insert_calls[0][0][0]
    assert conn.commit.call_count == 1


def test_register_already_registered(client, mock_db):
    """Registration fails if employee ID is already taken."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = (1,)  # ID already registered

    register_payload = {
        "userId": "EMP001",
        "fullName": "Duplicate Employee",
        "email": "duplicate@company.com",
        "password": "password123"
    }
    response = client.post("/api/auth/register", json=register_payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "Employee ID already registered"


def test_register_rate_limited(client, mock_db):
    """POST /api/auth/register is limited to 5/minute; the 6th call in a
    window returns 429."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = None

    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = True
    try:
        with patch("routers.auth.send_approval_email"):
            for i in range(5):
                payload = {
                    "userId": f"EMPRL{i}",
                    "fullName": "Rate Limit Test",
                    "email": "ratelimit@company.com",
                    "password": "password123",
                }
                r = client.post("/api/auth/register", json=payload)
                assert r.status_code == 200
            r = client.post("/api/auth/register", json=payload)
            assert r.status_code == 429
    finally:
        auth_limiter.enabled = False


# ── Approval Tests ────────────────────────────────────────────────────────────

def test_approve_user_success(client, mock_db, admin_cookies):
    """Admin/QA role can approve a user via valid signed token."""
    conn, cur = mock_db
    cur.fetchone.return_value = (False,)  # is_active = False originally

    valid_token = "valid_signed_token"
    
    with patch("routers.auth._ts.loads", return_value="EMP999"):
        response = client.get(f"/api/auth/approve/{valid_token}", cookies=admin_cookies)

    assert response.status_code == 200
    assert "approved and activated" in response.json()["message"]
    
    # Assert DB update query was executed
    update_calls = [
        call for call in cur.execute.call_args_list
        if "UPDATE users SET is_active = True" in call[0][0]
    ]
    assert len(update_calls) == 1
    assert update_calls[0][0][1] == ("active", "EMP999")
    assert conn.commit.call_count == 1


def test_approve_user_already_active(client, mock_db, admin_cookies):
    """Approving an already active user returns a friendly message and does no updates."""
    conn, cur = mock_db
    cur.fetchone.return_value = (True,)  # is_active = True originally

    valid_token = "valid_signed_token"
    
    with patch("routers.auth._ts.loads", return_value="EMP999"):
        response = client.get(f"/api/auth/approve/{valid_token}", cookies=admin_cookies)

    assert response.status_code == 200
    assert "already active" in response.json()["message"]
    assert conn.commit.call_count == 0  # No commit!


def test_approve_user_expired(client, admin_cookies):
    """Approving with an expired token returns 400."""
    valid_token = "expired_token"
    with patch("routers.auth._ts.loads", side_effect=SignatureExpired("Expired link")):
        response = client.get(f"/api/auth/approve/{valid_token}", cookies=admin_cookies)

    assert response.status_code == 400
    assert "expired" in response.json()["detail"]


def test_approve_user_bad_signature(client, admin_cookies):
    """Approving with a tampered signature returns 400."""
    valid_token = "bad_token"
    with patch("routers.auth._ts.loads", side_effect=BadSignature("Tampered token")):
        response = client.get(f"/api/auth/approve/{valid_token}", cookies=admin_cookies)

    assert response.status_code == 400
    assert "Invalid approval link" in response.json()["detail"]


def test_approve_user_unauthorized(client):
    """Approving a user without admin role fails with 401 or 403."""
    # Crucial: clear cookies to avoid session leakage from other tests
    client.cookies.clear()
    
    # Without login
    response = client.get("/api/auth/approve/some_token")
    assert response.status_code == 401

    # Non-admin user role
    from services.auth_service import create_access_token
    user_token = create_access_token({"sub": "EMP002", "name": "User", "role": "user"})
    response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": user_token})
    assert response.status_code == 403


def test_approve_user_rate_limited(client, mock_db, admin_cookies):
    """GET /api/auth/approve/{token} is limited to 5/minute; the 6th call
    in a window returns 429."""
    conn, cur = mock_db
    cur.fetchone.return_value = (True,)  # already-active short-circuits DB write path

    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = True
    try:
        with patch("routers.auth._ts.loads", return_value="EMP999"):
            for _ in range(5):
                r = client.get("/api/auth/approve/some_token", cookies=admin_cookies)
                assert r.status_code == 200
            r = client.get("/api/auth/approve/some_token", cookies=admin_cookies)
            assert r.status_code == 429
    finally:
        auth_limiter.enabled = False


# ── Logout Tests ──────────────────────────────────────────────────────────────

def test_logout_success(client, auth_cookies):
    """Logout clears the auth cookie."""
    response = client.post("/api/auth/logout", cookies=auth_cookies)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    # Assert cookie is cleared
    cookie = response.cookies.get("dpa_token")
    assert cookie == "" or cookie is None


# ── Session-version enforcement Tests ───────────────────────────────────────
#
# get_current_user is used across ~25 protected routes (via require_role too).
# We exercise it here through /api/auth/approve/{token}, which is gated by
# require_admin -> get_current_user, without touching product_request.py.

def test_get_current_user_old_token_no_sv_claim_passes_through(client, mock_db, admin_cookies):
    """A token minted without an `sv` claim (e.g. by the untouched make_token
    fixture) must NOT trigger any session_version DB lookup and must be let
    through exactly as before this feature existed."""
    conn, cur = mock_db
    cur.fetchone.return_value = (True,)  # already-active short-circuits further writes

    with patch("routers.auth._ts.loads", return_value="EMP999"):
        response = client.get("/api/auth/approve/some_token", cookies=admin_cookies)

    assert response.status_code == 200
    # No query should ever mention session_version for an sv-less token.
    for call in cur.execute.call_args_list:
        assert "session_version" not in call[0][0]


def test_get_current_user_sv_matches_session_version_passes(client, mock_db):
    """A token carrying `sv` that matches the DB's current session_version is
    accepted."""
    from services.auth_service import create_access_token

    conn, cur = mock_db
    # First fetchone: the sv-check SELECT; second: approve's is_active check.
    cur.fetchone.side_effect = [(1, "active"), (True,)]

    token = create_access_token({"sub": "admin", "name": "Admin User", "role": "admin", "sv": 1})
    with patch("routers.auth._ts.loads", return_value="EMP999"):
        response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": token})

    assert response.status_code == 200


def test_get_current_user_sv_mismatch_returns_401(client, mock_db):
    """A token carrying an `sv` that no longer matches users.session_version
    (e.g. because an admin reset the password / revoked sessions) is
    rejected with 401, reusing the standard invalid-token message."""
    from services.auth_service import create_access_token

    conn, cur = mock_db
    cur.fetchone.return_value = (1,)  # current session_version in DB

    token = create_access_token({"sub": "admin", "name": "Admin User", "role": "admin", "sv": 99})
    response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_get_current_user_rejects_disabled_account_even_when_session_version_matches(client, mock_db):
    """A disabled account's still-valid JWT must be rejected immediately."""
    from services.auth_service import create_access_token

    conn, cur = mock_db
    cur.fetchone.return_value = (1, "disabled")
    token = create_access_token({"sub": "admin", "name": "Admin User", "role": "admin", "sv": 1})

    response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_get_current_user_sv_present_user_not_found_returns_401(client, mock_db):
    """If the sv-bearing token's subject no longer exists, fail closed."""
    from services.auth_service import create_access_token

    conn, cur = mock_db
    cur.fetchone.return_value = None

    token = create_access_token({"sub": "ghost", "name": "Ghost", "role": "admin", "sv": 1})
    response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


def test_get_current_user_sv_present_db_unavailable_fails_closed(client, monkeypatch):
    """When `sv` is present but the DB connection cannot be established, the
    request must be rejected (401), not silently allowed through -- this is
    an authn check, so the fail-open convention used elsewhere does NOT
    apply here."""
    from services.auth_service import create_access_token
    from services import db_connector
    monkeypatch.setattr(db_connector.DBConnector, "get_dpa_connection",
                        staticmethod(lambda: None))

    token = create_access_token({"sub": "admin", "name": "Admin User", "role": "admin", "sv": 1})
    response = client.get("/api/auth/approve/some_token", cookies={"dpa_token": token})

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or expired token"


# ── Reset-password Tests ────────────────────────────────────────────────────

def test_reset_password_invalid_or_expired_token_returns_400(client, mock_db):
    """A token whose hash isn't found unused-and-unexpired (already used,
    expired, or never existed) returns 400 without leaking which case it
    was."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = None  # UPDATE ... RETURNING found no row

    response = client.post("/api/auth/reset-password/bad-token", json={"password": "NewPassw0rd!"})

    assert response.status_code == 400
    assert conn.commit.call_count == 0


def test_reset_password_success(client, mock_db):
    """A valid, unused, unexpired reset token: updates the bcrypt password,
    marks the token used, bumps session_version, and logs an audit event
    (self-service, no actor, no credential material)."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = ("EMP001",)  # RETURNING user_id

    raw_token = "raw-reset-token-value"
    expected_hash = hashlib.sha256(raw_token.encode()).hexdigest()

    response = client.post(
        f"/api/auth/reset-password/{raw_token}",
        json={"password": "NewPassw0rd!"},
    )

    assert response.status_code == 200

    # The consume-token UPDATE must be parameterized with the SHA-256 hash,
    # never the raw token.
    consume_calls = [
        call for call in cur.execute.call_args_list
        if "password_reset_tokens" in call[0][0] and "used_at" in call[0][0]
    ]
    assert len(consume_calls) == 1
    assert consume_calls[0][0][1] == (expected_hash,)

    # The password update + session_version bump happen in the same
    # transaction and are committed once.
    pw_calls = [
        call for call in cur.execute.call_args_list
        if "UPDATE users SET password_hash" in call[0][0]
    ]
    assert len(pw_calls) == 1
    assert "session_version" in pw_calls[0][0][0]
    assert pw_calls[0][0][1][-1] == "EMP001"
    assert conn.commit.call_count == 1

    audit_calls = [call for call in cur.execute.call_args_list if "INSERT INTO account_audit_logs" in call[0][0]]
    assert len(audit_calls) == 1
    assert conn.commit.call_count == 1
