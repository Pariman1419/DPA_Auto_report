"""
Unit tests for backend/services/db_connector.py pool lifecycle.

Covers PH-06 (singleton pool init under concurrent callers) and PH-07
(pool closes exactly once on app shutdown) from
docs/superpowers/plans/2026-08-27-production-hardening.md.

All tests mock psycopg2.pool.ThreadedConnectionPool -- no real DB is used.
"""
import threading
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_pool_state():
    """Ensure each test starts with a clean, uninitialized pool."""
    from services import db_connector
    db_connector.DBConnector._dpa_pool = None
    db_connector.DBConnector._last_init_failure_ts = None
    yield
    db_connector.DBConnector._dpa_pool = None
    db_connector.DBConnector._last_init_failure_ts = None


@pytest.mark.unit
def test_initialize_dpa_pool_is_singleton_under_concurrent_callers():
    """PH-06: two threads racing on first init must not construct two pools."""
    from services import db_connector

    fake_pool = MagicMock()
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ) as mock_ctor:
        results = []
        barrier = threading.Barrier(2)

        def _call():
            barrier.wait()  # maximize the chance both threads race past the None check
            results.append(db_connector.DBConnector.initialize_dpa_pool())

        t1 = threading.Thread(target=_call)
        t2 = threading.Thread(target=_call)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert mock_ctor.call_count == 1
        assert results[0] is fake_pool
        assert results[1] is fake_pool
        assert db_connector.DBConnector._dpa_pool is fake_pool


@pytest.mark.unit
def test_initialize_dpa_pool_is_idempotent_when_called_again():
    """Calling initialize_dpa_pool() again after it's already initialized
    must NOT construct a second pool."""
    from services import db_connector

    fake_pool = MagicMock()
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ) as mock_ctor:
        first = db_connector.DBConnector.initialize_dpa_pool()
        second = db_connector.DBConnector.initialize_dpa_pool()

        assert mock_ctor.call_count == 1
        assert first is second is fake_pool


@pytest.mark.unit
def test_close_dpa_pool_calls_closeall_once():
    """PH-07 (unit-level): close_dpa_pool() closes the underlying pool
    exactly once."""
    from services import db_connector

    fake_pool = MagicMock()
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ):
        db_connector.DBConnector.initialize_dpa_pool()

    db_connector.DBConnector.close_dpa_pool()

    fake_pool.closeall.assert_called_once()
    assert db_connector.DBConnector._dpa_pool is None


@pytest.mark.unit
def test_close_dpa_pool_is_safe_when_never_initialized():
    """close_dpa_pool() must be a no-op (not a crash) if the pool was never
    initialized."""
    from services import db_connector

    assert db_connector.DBConnector._dpa_pool is None
    db_connector.DBConnector.close_dpa_pool()  # should not raise
    assert db_connector.DBConnector._dpa_pool is None


@pytest.mark.unit
def test_close_dpa_pool_is_safe_when_called_twice():
    from services import db_connector

    fake_pool = MagicMock()
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ):
        db_connector.DBConnector.initialize_dpa_pool()

    db_connector.DBConnector.close_dpa_pool()
    db_connector.DBConnector.close_dpa_pool()  # second call: no-op, no crash

    fake_pool.closeall.assert_called_once()


@pytest.mark.unit
def test_get_dpa_connection_lazily_initializes_pool_via_locked_path():
    """Defensive fallback: get_dpa_connection() before lifespan init should
    route through the same locked initializer (no separate race path)."""
    from services import db_connector

    fake_pool = MagicMock()
    fake_conn = MagicMock()
    fake_pool.getconn.return_value = fake_conn
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ) as mock_ctor:
        conn = db_connector.DBConnector.get_dpa_connection()

        assert conn is fake_conn
        assert mock_ctor.call_count == 1


@pytest.mark.unit
def test_module_level_wrappers_delegate_to_dbconnector():
    """main.py imports module-level initialize_dpa_pool/close_dpa_pool
    (not the classmethods directly) for the lifespan handler."""
    from services import db_connector

    fake_pool = MagicMock()
    with patch.object(
        db_connector.psycopg2.pool, "ThreadedConnectionPool", return_value=fake_pool
    ):
        result = db_connector.initialize_dpa_pool()
        assert result is fake_pool
        assert db_connector.DBConnector._dpa_pool is fake_pool

    db_connector.close_dpa_pool()
    fake_pool.closeall.assert_called_once()
    assert db_connector.DBConnector._dpa_pool is None


@pytest.mark.unit
def test_lifespan_initializes_and_closes_pool_exactly_once(monkeypatch):
    """PH-07: the app's lifespan context manager calls initialize_dpa_pool()
    once before yield and close_dpa_pool() once after -- exercised directly
    (not via TestClient/app fixture) so this test doesn't disturb the
    session-scoped app used by the rest of the suite."""
    import asyncio
    import main as main_module

    init_mock = MagicMock()
    close_mock = MagicMock()
    monkeypatch.setattr(main_module, "initialize_dpa_pool", init_mock)
    monkeypatch.setattr(main_module, "close_dpa_pool", close_mock)

    async def _run():
        async with main_module.lifespan(main_module.app):
            init_mock.assert_called_once()
            close_mock.assert_not_called()
        close_mock.assert_called_once()

    asyncio.run(_run())
