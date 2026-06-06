import os
import smtplib
from email.message import EmailMessage
from typing import Optional

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
from models.schemas import LoginRequest, RegisterRequest, TokenResponse
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
    """Extract and validate JWT from httpOnly cookie (primary) or Bearer header (fallback)."""
    token = request.cookies.get(_COOKIE_NAME)
    if not token and credentials:
        token = credentials.credentials
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        return decode_token(token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


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
                "SELECT user_id, full_name, role, password_hash "
                "FROM users WHERE user_id = %s AND is_active = True",
                (req.userId,),
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

        token = create_access_token({
            "sub":  user["user_id"],
            "name": user["full_name"],
            "role": user["role"],
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
def logout(response: Response):
    """Clear the auth cookie."""
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
def register(req: RegisterRequest):
    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise HTTPException(status_code=503, detail="Database unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s", (req.userId,))
            if cur.fetchone():
                raise HTTPException(status_code=409, detail="Employee ID already registered")

            cur.execute(
                "INSERT INTO users (user_id, full_name, email, role, password_hash, is_active) "
                "VALUES (%s, %s, %s, %s, %s, False)",
                (req.userId, req.fullName, req.email or None, "user", hash_password(req.password)),
            )
        conn.commit()

        send_approval_email(req.userId, req.fullName, req.email or "")
        return {"status": "success", "message": "Account created. Please wait for admin approval."}
    finally:
        DBConnector.release_dpa_connection(conn)


@router.get("/approve/{token}")
def approve_user(token: str, _admin=Depends(require_admin)):
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

            cur.execute("UPDATE users SET is_active = True WHERE user_id = %s", (user_id,))
        conn.commit()
        log.info("User %s approved by admin", user_id)
        return {"message": f"User {user_id} has been approved and activated."}
    finally:
        DBConnector.release_dpa_connection(conn)
