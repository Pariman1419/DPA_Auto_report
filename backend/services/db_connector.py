import os
import sys
import threading
import time
import psycopg2
import psycopg2.pool
import oracledb

from logger import get_logger

log = get_logger("db_connector")

# ---------------------------------------------------------------------------
# Startup validation — fail fast if required env vars are missing
# ---------------------------------------------------------------------------

def _require(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        log.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return val


DPA_CONFIG = {
    "host":          _require("DB_HOST"),
    "port":          os.getenv("DB_PORT", "5432"),
    "database":      os.getenv("DB_NAME", "DPA"),
    "user":          _require("DB_USER"),
    "password":      _require("DB_PASSWORD"),
    "connect_timeout": 10,
}

DW_CONFIG = {
    "user":     os.getenv("DW_USER", ""),
    "password": os.getenv("DW_PASSWORD", ""),
    "dsn":      os.getenv("DW_DSN", ""),
}


class DBConnector:
    _dpa_pool = None
    _pool_lock = threading.Lock()
    _last_init_failure_ts = None
    _INIT_RETRY_COOLDOWN_SECONDS = 30

    @classmethod
    def initialize_dpa_pool(cls):
        """Idempotently construct the DPA PostgreSQL connection pool.

        Safe to call concurrently from multiple threads (e.g. racing
        first requests before the app lifespan has finished starting up) --
        only one caller will ever construct the pool; the rest reuse it.
        Safe to call again after the pool already exists -- it's a no-op
        that returns the existing pool.

        Fails open (logs and returns None) rather than raising when the pool
        can't be constructed -- e.g. the DB is unreachable at startup. This is
        deliberate and load-bearing: tests/conftest.py runs the real FastAPI
        lifespan via TestClient(app) as a context manager for the whole test
        suite, and a fail-fast pool init would break every API test on any
        machine without a local Postgres reachable at DB_HOST (PH-10's
        "default suite is deterministic" requirement). Do not change this to
        fail-fast without also reworking the test fixtures.

        Retry cooldown: if a prior attempt in this process failed recently
        (within _INIT_RETRY_COOLDOWN_SECONDS), re-entries return None
        immediately instead of acquiring the lock and attempting another
        construction. Without this, every caller of get_dpa_connection()
        (including per-request telemetry in main.py, which runs on every
        non-/health request) would queue up behind each other's slow
        connect_timeout=10s attempts while the DB is down/unreachable,
        serializing request threads that don't even touch the DB.
        """
        if cls._dpa_pool is not None:
            return cls._dpa_pool
        if cls._last_init_failure_ts is not None:
            elapsed = time.monotonic() - cls._last_init_failure_ts
            if elapsed < cls._INIT_RETRY_COOLDOWN_SECONDS:
                return None
        with cls._pool_lock:
            if cls._dpa_pool is None:
                # Re-check cooldown inside the lock: another thread may have
                # just failed an attempt while we were waiting to acquire it.
                if (
                    cls._last_init_failure_ts is not None
                    and time.monotonic() - cls._last_init_failure_ts < cls._INIT_RETRY_COOLDOWN_SECONDS
                ):
                    return None
                try:
                    cls._dpa_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, **DPA_CONFIG)
                    cls._last_init_failure_ts = None
                except Exception as e:
                    log.error("Failed to initialize DPA connection pool: %s", e)
                    cls._dpa_pool = None
                    cls._last_init_failure_ts = time.monotonic()
        return cls._dpa_pool

    @classmethod
    def close_dpa_pool(cls):
        """Close all pooled connections. Safe to call even if the pool was
        never initialized (no-op), and safe to call more than once."""
        with cls._pool_lock:
            pool, cls._dpa_pool = cls._dpa_pool, None
        if pool is not None:
            try:
                pool.closeall()
            except Exception as e:
                log.error("Error closing DPA connection pool: %s", e)

    @classmethod
    def get_dpa_connection(cls):
        """Get connection from PostgreSQL pool (DPA project).

        Defensive fallback: normally the app lifespan calls
        initialize_dpa_pool() at startup, but if this is somehow reached
        before that (e.g. a script run without the FastAPI lifespan), lazily
        initialize the pool here -- routed through the same locked
        initializer so no race is reintroduced.
        """
        if cls._dpa_pool is None:
            cls.initialize_dpa_pool()
        if cls._dpa_pool is None:
            return None
        try:
            return cls._dpa_pool.getconn()
        except psycopg2.pool.PoolError as e:
            log.error("DB connection pool exhausted: %s", e)
            return None

    @classmethod
    def release_dpa_connection(cls, conn):
        if cls._dpa_pool and conn:
            cls._dpa_pool.putconn(conn)

    @classmethod
    def get_dw_connection(cls):
        """Get connection to Oracle Datawarehouse."""
        if not DW_CONFIG["user"] or not DW_CONFIG["dsn"]:
            log.warning("DW_USER or DW_DSN not configured — skipping DW query")
            return None
        try:
            return oracledb.connect(
                user=DW_CONFIG["user"],
                password=DW_CONFIG["password"],
                dsn=DW_CONFIG["dsn"],
            )
        except oracledb.DatabaseError as e:
            log.error("Error connecting to Datawarehouse: %s", e)
            return None


# ---------------------------------------------------------------------------
# Module-level convenience wrappers for the FastAPI lifespan (main.py)
# ---------------------------------------------------------------------------

def initialize_dpa_pool():
    """Called once from the app lifespan at startup."""
    return DBConnector.initialize_dpa_pool()


def close_dpa_pool():
    """Called once from the app lifespan at shutdown."""
    DBConnector.close_dpa_pool()
