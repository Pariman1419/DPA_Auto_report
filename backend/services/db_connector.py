import os
import sys
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
        print(f"[ERROR] Required environment variable '{name}' is not set.", file=sys.stderr)
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

    @classmethod
    def get_dpa_connection(cls):
        """Get connection from PostgreSQL pool (DPA project)."""
        if cls._dpa_pool is None:
            cls._dpa_pool = psycopg2.pool.ThreadedConnectionPool(1, 10, **DPA_CONFIG)
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
