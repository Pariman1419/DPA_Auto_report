import hashlib
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from jose import JWTError
from psycopg2.extras import RealDictCursor
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.auth_service import (
    verify_password, hash_password, is_bcrypt_hash,
    create_access_token, decode_token,
    ACCESS_TOKEN_EXPIRE_HOURS, SECRET_KEY,
)
from services.db_connector import DBConnector
from services.audit_service import AuditEvent, write_audit_event, insert_audit_event, mirror_event
from models.schemas import LoginRequest, RegisterRequest, TokenResponse, ResetPasswordRequest
from logger import get_logger

log = get_logger("auth")

router = APIRouter(prefix="/api/auth", tags=["Auth"])
_bearer = HTTPBearer(auto_error=False)
limiter = Limiter(key_func=get_remote_address)

_COOKIE_NAME    = "dpa_token"
_COOKIE_MAX_AGE = ACCESS_TOKEN_EXPIRE_HOURS * 3600
_COOKIE_SECURE  = os.getenv("COOKIE_SECURE", "false").lower() == "true"

SMTP_HOST      = os.environ.get("SMTP_HOST", "")
SMTP_PORT      = int(os.environ.get("SMTP_PORT", "25"))
APPROVER_EMAIL = os.environ.get("APPROVER_EMAIL", "")
SENDER_EMAIL   = os.environ.get("SENDER_EMAIL", "")
BASE_URL       = os.environ.get("BASE_URL", "http://localhost:9090")

_APPROVAL_MAX_AGE = 86400  # 24 hours
_ts = URLSafeTimedSerializer(SECRET_KEY)


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """Extract and validate JWT from httpOnly cookie (primary) or Bearer header (fallback).

    Tokens minted before the `sv` (session_version) claim existed -- i.e. any
    token without that claim -- are honored exactly as before this feature
    was added; no DB lookup is performed. Tokens carrying `sv` are checked
    against the live users.session_version so an admin-triggered password
    reset / session revocation can invalidate them. That check fails CLOSED
    (401) if the DB is unavailable, since this is an authentication gate, not
    a best-effort telemetry/audit write.
    """
    token = request.cookies.get(_COOKIE_NAME)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    sv = payload.get("sv")
    if sv is not None:
        conn = DBConnector.get_dpa_connection()
        if not conn:
            raise HTTPException(status_code=401, detail="Invalid or expired token")
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT session_version, account_status FROM users WHERE user_id = %s",
                    (payload.get("sub"),),
                )
                row = cur.fetchone()
                if not row or row[0] != sv or row[1] != "active":
                    raise HTTPException(status_code=401, detail="Invalid or expired token")
                session_id = payload.get("sid")
                if session_id:
                    cur.execute("UPDATE user_sessions SET last_seen_at = now() WHERE session_id = %s", (session_id,))
                    conn.commit()
        finally:
            DBConnector.release_dpa_connection(conn)

    return payload


def require_role(*roles: str):
    """Dependency factory — raises 403 if the authenticated user's role is not in roles."""
    def checker(user: dict = Depends(get_current_user)) -> dict:
        if user.get("role") not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


require_admin = require_role("admin", "QA Engineer")


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
def login(request: Request, req: LoginRequest, response: Response):
    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT user_id, full_name, role, password_hash, session_version "
                "FROM users WHERE user_id = %s AND account_status = %s AND is_active = True",
                (req.userId, "active"),
            )
            user = cur.fetchone()

        if not user or not verify_password(req.password, user["password_hash"]):
            raise HTTPException(status_code=401, detail="Invalid Employee ID or password")

        # Upgrade plain-text password to bcrypt on first successful login
        if not is_bcrypt_hash(user["password_hash"]):
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE user_id = %s",
                    (hash_password(req.password), req.userId),
                )
            conn.commit()

        session_expires_at = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
        session_id = str(uuid4())
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_sessions (user_id, session_id, ip_address, user_agent, expires_at, last_seen_at) "
                "VALUES (%s, %s, %s, %s, %s, now())",
                (
                    user["user_id"],
                    session_id,
                    request.client.host if request.client else None,
                    request.headers.get("user-agent"),
                    session_expires_at,
                ),
            )
        conn.commit()

        token = create_access_token({
            "sub":  user["user_id"],
            "name": user["full_name"],
            "role": user["role"],
            "sv":   user["session_version"],
            "sid":  str(session_id),
        })

        response.set_cookie(
            key=_COOKIE_NAME,
            value=token,
            httponly=True,
            secure=_COOKIE_SECURE,
            max_age=_COOKIE_MAX_AGE,
            samesite="lax",
            path="/",
        )

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            user={"userId": user["user_id"], "fullName": user["full_name"], "role": user["role"]},
        )
    finally:
        DBConnector.release_dpa_connection(conn)


@router.post("/logout")
def logout(request: Request, response: Response):
    """Clear the auth cookie."""
    token = request.cookies.get(_COOKIE_NAME)
    if token:
        try:
            session_id = decode_token(token).get("sid")
            if session_id:
                conn = DBConnector.get_dpa_connection()
                if conn:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("UPDATE user_sessions SET logged_out_at = now() WHERE session_id = %s", (session_id,))
                        conn.commit()
                    finally:
                        DBConnector.release_dpa_connection(conn)
        except Exception:
            log.warning("Failed to record logout session state")
    response.delete_cookie(key=_COOKIE_NAME, path="/")
    return {"status": "ok"}


def send_approval_email(user_id: str, full_name: str, email: str):
    """Send an approval-request email to the admin using a time-limited signed token."""
    if not APPROVER_EMAIL or not SMTP_HOST:
        log.warning("SMTP not configured — approval email not sent for user %s", user_id)
        return

    token = _ts.dumps(user_id, salt="user-approval")
    approve_link = f"{BASE_URL}/api/auth/approve/{token}"

    log.info("Sending approval email to %s for user %s", APPROVER_EMAIL, user_id)

    msg = EmailMessage()
    msg["Subject"] = f"DPA Report - New User Registration Request: {full_name}"
    msg["From"]    = SENDER_EMAIL or APPROVER_EMAIL
    msg["To"]      = APPROVER_EMAIL
    msg.set_content(
        f"Hello Admin,\n\n"
        f"A new user has registered and is waiting for approval.\n\n"
        f"User ID: {user_id}\nName: {full_name}\nEmail: {email or 'N/A'}\n\n"
        f"Approve link (valid 24 hours): {approve_link}\n\nThank you,\nDPA Report System"
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.send_message(msg)
        log.info("Approval email sent to %s", APPROVER_EMAIL)
    except Exception as e:
        log.error("Failed to send approval email: %s", e)


@router.post("/register")
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest):
    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s", (req.userId,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Employee ID already registered")

            cur.execute(
                "INSERT INTO users (user_id, full_name, email, role, password_hash, is_active, account_status) "
                "VALUES (%s, %s, %s, %s, %s, False, %s)",
                (req.userId, req.fullName, req.email or None, "user", hash_password(req.password), "pending"),
            )
        conn.commit()

        send_approval_email(req.userId, req.fullName, req.email or "")
        return {"status": "success", "message": "Account created. Please wait for admin approval."}
    finally:
        DBConnector.release_dpa_connection(conn)


@router.get("/approve/{token}")
@limiter.limit("5/minute")
def approve_user(request: Request, token: str, _admin=Depends(require_admin)):
    """Admin-only endpoint to activate a pending user account (token expires in 24h)."""
    try:
        user_id = _ts.loads(token, salt="user-approval", max_age=_APPROVAL_MAX_AGE)
    except SignatureExpired:
        raise HTTPException(status_code=400, detail="Approval link has expired (>24h)")
    except BadSignature:
        raise HTTPException(status_code=400, detail="Invalid approval link")

    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT is_active FROM users WHERE user_id = %s", (user_id,))
            user = cur.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            if user[0]:
                return {"message": f"User {user_id} is already active."}

            cur.execute("UPDATE users SET is_active = True, account_status = %s WHERE user_id = %s", ("active", user_id))
        conn.commit()
        log.info("User %s approved by admin", user_id)
        return {"message": f"User {user_id} has been approved and activated."}
    finally:
        DBConnector.release_dpa_connection(conn)


@router.post("/reset-password/{token}")
@limiter.limit("5/minute")
def reset_password(request: Request, token: str, req: ResetPasswordRequest):
    """
    Consume a one-time password reset link (issued by
    account_admin_service.create_reset_link). The raw token from the URL is
    hashed the same way it was stored (SHA-256) and looked up in
    password_reset_tokens; never the itsdangerous-signed mechanism used for
    approval links.

    Atomic per-request: the "is this token still valid" check and the
    consuming UPDATE happen together (UPDATE ... WHERE used_at IS NULL AND
    expires_at > now() RETURNING user_id) so a token can only ever be spent
    once, even under concurrent requests. If it returns no row, the token
    was already used, expired, or never existed -- always reported as a
    generic 400 to avoid leaking which case it was. On success, the password
    update and the session_version bump happen in the same transaction and
    are committed together, so a reset can never invalidate sessions without
    actually changing the password (or vice versa).
    """
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE password_reset_tokens SET used_at = now() "
                "WHERE token_hash = %s AND used_at IS NULL AND revoked_at IS NULL AND expires_at > now() "
                "RETURNING user_id",
                (token_hash,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="Invalid or expired reset link")
            user_id = row[0]

            cur.execute(
                "UPDATE users SET password_hash = %s, session_version = session_version + 1 "
                "WHERE user_id = %s",
                (hash_password(req.password), user_id),
            )
            event = AuditEvent(
                actor_user_id=None, target_user_id=user_id, action="password_reset",
                before_state=None, after_state={"method": "reset_link"},
            )
            insert_audit_event(cur, event)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        DBConnector.release_dpa_connection(conn)

    mirror_event(event)
    log.info("Password reset via reset link for user %s", user_id)
    return {"status": "success", "message": "Password has been reset."}
