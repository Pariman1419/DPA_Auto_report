"""
Unit tests for services/auth_service.py

Tests: hash_password, verify_password, is_bcrypt_hash,
       create_access_token, decode_token
No DB, no HTTP — pure function tests.
"""
import os
import sys
import pytest
from datetime import datetime, timezone, timedelta

# env vars set by conftest.py before this import
from services.auth_service import (
    hash_password, verify_password, is_bcrypt_hash,
    create_access_token, decode_token,
    ACCESS_TOKEN_EXPIRE_HOURS, ALGORITHM,
)
from jose import jwt, JWTError

SECRET = os.environ["JWT_SECRET_KEY"]

pytestmark = pytest.mark.unit


# ── is_bcrypt_hash ────────────────────────────────────────────────────────────

def test_is_bcrypt_hash_recognises_2b_prefix():
    assert is_bcrypt_hash("$2b$12$somehashvalue") is True

def test_is_bcrypt_hash_recognises_2a_prefix():
    assert is_bcrypt_hash("$2a$12$somehashvalue") is True

def test_is_bcrypt_hash_rejects_plaintext():
    assert is_bcrypt_hash("plainpassword") is False

def test_is_bcrypt_hash_rejects_empty():
    assert is_bcrypt_hash("") is False

def test_is_bcrypt_hash_rejects_sha_prefix():
    assert is_bcrypt_hash("sha256$abc123") is False


# ── hash_password ─────────────────────────────────────────────────────────────

def test_hash_password_produces_bcrypt_hash():
    h = hash_password("secret")
    assert is_bcrypt_hash(h)

def test_hash_password_produces_different_salts():
    h1 = hash_password("same_password")
    h2 = hash_password("same_password")
    assert h1 != h2  # different salts → different hashes

def test_hash_password_not_plaintext():
    assert hash_password("secret") != "secret"


# ── verify_password ───────────────────────────────────────────────────────────

def test_verify_password_correct():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True

def test_verify_password_wrong():
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False

def test_verify_password_rejects_plaintext_hash():
    # Legacy plain-text hash must NOT authenticate via verify_password
    # (upgrade path: frontend logs in, backend upgrades hash on success)
    assert verify_password("plainpassword", "plainpassword") is False

def test_verify_password_empty_password():
    h = hash_password("notempty")
    assert verify_password("", h) is False

def test_verify_password_empty_hash():
    assert verify_password("anything", "") is False


# ── create_access_token ───────────────────────────────────────────────────────

def test_create_access_token_returns_decodable_jwt():
    token = create_access_token({"sub": "EMP001", "name": "Test", "role": "QA Engineer"})
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    assert payload["sub"] == "EMP001"
    assert payload["role"] == "QA Engineer"

def test_create_access_token_contains_expiry():
    token = create_access_token({"sub": "EMP001"})
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    assert "exp" in payload

def test_create_access_token_expiry_is_future():
    token = create_access_token({"sub": "EMP001"})
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    assert exp > datetime.now(timezone.utc)

def test_create_access_token_expiry_duration():
    before = datetime.now(timezone.utc)
    token = create_access_token({"sub": "EMP001"})
    payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    expected_delta = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    # Allow 5 second clock skew
    assert abs((exp - before - expected_delta).total_seconds()) < 5


# ── decode_token ──────────────────────────────────────────────────────────────

def test_decode_token_roundtrip():
    payload_in = {"sub": "EMP001", "name": "Alice", "role": "admin"}
    token = create_access_token(payload_in)
    payload_out = decode_token(token)
    assert payload_out["sub"] == "EMP001"
    assert payload_out["role"] == "admin"

def test_decode_token_raises_on_tampered_token():
    token = create_access_token({"sub": "EMP001"})
    tampered = token[:-5] + "XXXXX"
    with pytest.raises(JWTError):
        decode_token(tampered)

def test_decode_token_raises_on_wrong_secret():
    token = jwt.encode({"sub": "EMP001", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                       "wrong-secret", algorithm=ALGORITHM)
    with pytest.raises(JWTError):
        decode_token(token)

def test_decode_token_raises_on_expired():
    expired_token = jwt.encode(
        {"sub": "EMP001", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
        SECRET, algorithm=ALGORITHM,
    )
    with pytest.raises(JWTError):
        decode_token(expired_token)

def test_decode_token_raises_on_empty_string():
    with pytest.raises(JWTError):
        decode_token("")
