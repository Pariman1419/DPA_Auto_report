import os
import sys
from datetime import datetime, timezone, timedelta

import bcrypt
from jose import jwt

from logger import get_logger

log = get_logger("auth_service")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    log.error("JWT_SECRET_KEY is not set. Set it in .env before starting.")
    sys.exit(1)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 8


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Verify password using bcrypt only. Plain-text hashes are rejected."""
    if not is_bcrypt_hash(hashed):
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except bcrypt.exceptions.InvalidHashError:
        return False


def is_bcrypt_hash(value: str) -> bool:
    return value.startswith("$2b$") or value.startswith("$2a$")


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
