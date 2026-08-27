import os
import sys
import threading
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

    @classmethod
    def initialize_dpa_pool(cls):
        """Idempotently construct the DPA PostgreSQL connection pool.

        Safe to call concurrently from multiple threads (e.g. racing
        first requests before the app lifespan has finished starting up) --
        only one caller will ever construct the pool; the rest reuse it.
        Safe to call again after the pool already exists -- it's a no-op
        that returns the existing pool.
        """
        if cls._dpa_pool is not None:
            return cls._dpa_pool
        with cls._pool_lock:
            if cls._dpa_pool is None:
                try:
                    cls._dpa_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, **DPA_CONFIG)
                except Exception as e:
                    log.error("Failed to initialize DPA connection pool: %s", e)
                    cls._dpa_pool = None
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
