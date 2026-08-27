-- Migration 050: Account administration & observability schema
-- Adds account lifecycle/session columns to `users`, plus new tables for
-- audit logging, session tracking, request telemetry and password resets.
--
-- Idempotent: safe to run multiple times against the same database.
-- Run as: psql -h <host> -U postgres -d DPA -f backend/migrations/050_account_administration.sql

-- ---------------------------------------------------------------------------
-- users: lifecycle / session columns
-- ---------------------------------------------------------------------------
ALTER TABLE users ADD COLUMN IF NOT EXISTS account_status VARCHAR(20) NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS session_version INTEGER NOT NULL DEFAULT 1;

-- ---------------------------------------------------------------------------
-- account_audit_logs — records admin actions taken against a user account
-- (activate/deactivate/role change/etc). before_state/after_state capture a
-- JSON snapshot of the affected fields; never store credentials/tokens here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS account_audit_logs (
    id              BIGSERIAL     PRIMARY KEY,
    actor_user_id   VARCHAR(50),
    target_user_id  VARCHAR(50)   NOT NULL,
    action          VARCHAR(100)  NOT NULL,
    before_state    JSONB,
    after_state     JSONB,
    occurred_at     TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_account_audit_logs_target_occurred
    ON account_audit_logs (target_user_id, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- user_sessions — active/expired login sessions, used to support session
-- revocation (bump users.session_version to invalidate outstanding JWTs).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_sessions (
    id          BIGSERIAL     PRIMARY KEY,
    user_id     VARCHAR(50)   NOT NULL,
    ip_address  VARCHAR(64),
    user_agent  TEXT,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMPTZ,
    revoked_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_user_sessions_user_created
    ON user_sessions (user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- request_telemetry — per-request timing/status, prunable at 90 days.
-- Never store request bodies, query strings, or headers here.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS request_telemetry (
    id           BIGSERIAL     PRIMARY KEY,
    user_id      VARCHAR(50),
    route        VARCHAR(200)  NOT NULL,
    method       VARCHAR(10),
    status_code  INTEGER,
    duration_ms  INTEGER,
    occurred_at  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_request_telemetry_user_occurred
    ON request_telemetry (user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_request_telemetry_route_occurred
    ON request_telemetry (route, occurred_at DESC);

-- ---------------------------------------------------------------------------
-- endpoint_latency_daily — daily rollup of request_telemetry per route.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS endpoint_latency_daily (
    id              BIGSERIAL     PRIMARY KEY,
    route           VARCHAR(200)  NOT NULL,
    day             DATE          NOT NULL,
    request_count   INTEGER       NOT NULL DEFAULT 0,
    error_count     INTEGER       NOT NULL DEFAULT 0,
    avg_latency_ms  NUMERIC,
    p95_latency_ms  NUMERIC,
    max_latency_ms  NUMERIC,
    created_at      TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (route, day)
);

CREATE INDEX IF NOT EXISTS idx_endpoint_latency_daily_created
    ON endpoint_latency_daily (created_at DESC);

-- ---------------------------------------------------------------------------
-- password_reset_tokens — stores only a hash of the reset token, never the
-- raw token value.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id          BIGSERIAL     PRIMARY KEY,
    user_id     VARCHAR(50)   NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash  VARCHAR(128)  NOT NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMPTZ   NOT NULL,
    used_at     TIMESTAMPTZ,
    UNIQUE (token_hash)
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
    ON password_reset_tokens (user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_created
    ON password_reset_tokens (created_at DESC);
