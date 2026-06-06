"""
API tests for /api/auth/* endpoints.
Uses FastAPI TestClient and a mocked DB connector.
"""
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
    cur.execute.assert_called_with(
        "SELECT user_id, full_name, role, password_hash FROM users WHERE user_id = %s AND is_active = True",
        ("EMP001",)
    )


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
    assert conn.commit.call_count == 1


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
    assert update_calls[0][0][1][0] == "EMP999"
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


# ── Logout Tests ──────────────────────────────────────────────────────────────

def test_logout_success(client, auth_cookies):
    """Logout clears the auth cookie."""
    response = client.post("/api/auth/logout", cookies=auth_cookies)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    
    # Assert cookie is cleared
    cookie = response.cookies.get("dpa_token")
    assert cookie == "" or cookie is None
