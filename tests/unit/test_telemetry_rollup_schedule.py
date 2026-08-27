"""
Unit tests for the in-process daily telemetry-rollup scheduler in
backend/main.py (_seconds_until_next_rollup, _daily_rollup_loop, and its
lifespan wiring). This is what keeps endpoint_latency_daily populated
without needing an external cron/Task Scheduler entry.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


def test_seconds_until_next_rollup_same_day():
    import main as main_module

    now = datetime(2026, 8, 27, 10, 0, 0, tzinfo=timezone.utc)  # before 00:05 today's already passed... use hour 12
    with patch.object(main_module, "_ROLLUP_HOUR_UTC", 12):
        seconds = main_module._seconds_until_next_rollup(now)
    target = now.replace(hour=12, minute=5, second=0, microsecond=0)
    assert seconds == pytest.approx((target - now).total_seconds())
    assert seconds > 0


def test_seconds_until_next_rollup_rolls_to_tomorrow_when_slot_passed():
    import main as main_module

    now = datetime(2026, 8, 27, 23, 0, 0, tzinfo=timezone.utc)
    with patch.object(main_module, "_ROLLUP_HOUR_UTC", 0):
        seconds = main_module._seconds_until_next_rollup(now)
    target = datetime(2026, 8, 28, 0, 5, 0, tzinfo=timezone.utc)
    assert seconds == pytest.approx((target - now).total_seconds())


def test_daily_rollup_loop_calls_rollup_with_yesterdays_date(monkeypatch):
    import main as main_module

    rollup_mock = MagicMock(return_value=3)
    monkeypatch.setattr(main_module.telemetry_service, "rollup_daily_latency", rollup_mock)

    call_count = {"n": 0}

    async def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main_module._daily_rollup_loop())

    rollup_mock.assert_called_once()
    (called_date,) = rollup_mock.call_args.args
    expected = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    assert called_date == expected


def test_daily_rollup_loop_survives_rollup_failure_and_keeps_looping(monkeypatch):
    """A failed rollup must not crash the loop -- same fail-open spirit as
    telemetry recording itself."""
    import main as main_module

    rollup_mock = MagicMock(side_effect=RuntimeError("db down"))
    monkeypatch.setattr(main_module.telemetry_service, "rollup_daily_latency", rollup_mock)

    call_count = {"n": 0}

    async def fake_sleep(_seconds):
        call_count["n"] += 1
        if call_count["n"] > 1:
            raise asyncio.CancelledError()

    monkeypatch.setattr(main_module.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main_module._daily_rollup_loop())

    rollup_mock.assert_called_once()


def test_lifespan_starts_and_cancels_rollup_task(monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "initialize_dpa_pool", MagicMock())
    monkeypatch.setattr(main_module, "close_dpa_pool", MagicMock())

    started = asyncio.Event()

    async def fake_loop():
        started.set()
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise

    monkeypatch.setattr(main_module, "_daily_rollup_loop", fake_loop)

    async def _run():
        async with main_module.lifespan(main_module.app):
            await started.wait()

    asyncio.run(_run())  # must return -- proves the background task was cancelled and awaited, not left dangling
