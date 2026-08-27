# Task 5 Report: Capture usage and latency safely

## Summary

Implemented request telemetry recording, daily latency rollup, and a
retention purge script for the account-administration/observability
schema built in Task 1.

## Files created

- `backend/services/telemetry_service.py`
  - `record_request_telemetry(request_id=None, user_id=None, route="", method=None, status_code=None, duration_ms=None)`
    — inserts one row into `request_telemetry`. Whole body wrapped in
    `try/except Exception: log.warning(...)` so a DB hiccup (pool
    exhausted, connection refused, etc.) never raises out of this function.
    Does **not** persist `request_id` as a column — `request_telemetry`
    (per `backend/migrations/050_account_administration.sql`) has no such
    column; `request_id` is accepted only for future log/trace correlation.
  - `rollup_daily_latency(target_date=None)` — aggregates one calendar
    day of `request_telemetry` into `endpoint_latency_daily`, grouped by
    `route`, via `INSERT ... ON CONFLICT (route, day) DO UPDATE`. Uses the
    half-open predicate `occurred_at >= day_start AND occurred_at < day_start + 1 day`
    (both `TIMESTAMPTZ`), never `DATE(occurred_at) = %s`, to stay aligned
    with the `(route, occurred_at DESC)` index from Task 1. Computes
    `request_count`, `error_count` (`status_code >= 400`), `avg_latency_ms`,
    `p95_latency_ms` (`percentile_cont(0.95) WITHIN GROUP (ORDER BY duration_ms)`),
    `max_latency_ms`.
    - **Default-date judgment call**: defaults to **today** (UTC), not
      yesterday, when `target_date` is omitted. Rationale: this function has
      no scheduling opinion of its own — a scheduled nightly job (out of
      scope for this task) should explicitly pass yesterday's date; an
      ad-hoc/manual/admin-triggered call (the more likely caller of the
      bare default) more usefully rolls up "today" — the day someone is
      actually looking at. Documented in the function's docstring.
- `backend/scripts/purge_account_observability.py` (+ `backend/scripts/__init__.py`,
  matching the existing `services/`, `routers/`, `models/` package layout)
  - `purge()` — deletes rows past retention for 5 tables, returns
    `{table_name: rows_deleted}`, logs only the summary counts (never row
    contents):
    - `request_telemetry`: `occurred_at < now() - interval '90 days'`
    - `account_audit_logs`: `occurred_at < now() - interval '1 year'`
    - `user_sessions`: `started_at < now() - interval '1 year'`
    - `endpoint_latency_daily`: `created_at < now() - interval '1 year'`
    - `password_reset_tokens` (bonus item, schema-driven, not in the
      brief's own test-scenario list but called out in the design spec's
      data-model table): `(used_at IS NOT NULL AND used_at < now() - interval '7 days') OR (used_at IS NULL AND expires_at < now() - interval '7 days')`
  - `main()` / `if __name__ == "__main__":` entry point. Verified each
    table's timestamp column name against the migration file before writing
    predicates (`account_audit_logs.occurred_at`, `user_sessions.started_at`,
    `endpoint_latency_daily.created_at`, matching migration comments/notes
    about the `created_at` → `started_at` rename).
- `tests/api/test_telemetry.py` (5 tests)
- `tests/unit/test_retention.py` (5 tests)

## Files modified

- `backend/main.py` (middleware extension only, per scope)
  - Added `from uuid import uuid4`, `from jose import JWTError`,
    `from services.auth_service import decode_token`, `from services import telemetry_service`.
  - `request_log_middleware` now: assigns `request.state.request_id = uuid4()`
    at the start; after `call_next`, resolves the **templated** route via
    `request.scope.get("route")` (falling back to `request.url.path` for
    unmatched routes); skips telemetry recording entirely when
    `request.url.path == "/health"` (checked on the raw path, per spec);
    extracts `actor_user_id` best-effort via a new `_extract_actor_user_id`
    helper (cookie `dpa_token` first, then `Authorization: Bearer`,
    mirroring `get_current_user`'s order) that catches `JWTError` and any
    other decode failure and returns `None` — never raises; calls
    `telemetry_service.record_request_telemetry(...)` **plainly** (no
    try/except in the middleware — fail-open behavior lives entirely inside
    `record_request_telemetry` itself, per the task's design decision).
  - Imported the module (`from services import telemetry_service`) rather
    than the function directly, so tests can patch
    `services.telemetry_service.record_request_telemetry` and have that
    patch actually take effect at the middleware's call site (patching a
    `from x import y`-style name binding would not have worked).
  - Existing `log.info(...)` request line left untouched.
- `tests/conftest.py` — added one new fixture, `_default_stub_telemetry`
  (autouse): since `request_log_middleware` now calls
  `record_request_telemetry` on every request that goes through the
  `client` fixture, and `mock_db` hands every caller (including
  `telemetry_service`) the *same* shared mock connection, the new
  post-response `conn.commit()` from telemetry recording was inflating
  pre-existing tests' `conn.commit.call_count` assertions in
  `tests/api/test_auth.py` (6 tests started failing: `test_login_password_upgrade`,
  `test_register_success`, `test_approve_user_success`,
  `test_approve_user_already_active`, `test_reset_password_invalid_or_expired_token_returns_400`,
  `test_reset_password_success` — all off by exactly the one extra
  telemetry commit). Rather than touch those pre-existing Task 1–4 test
  files (out of scope), added an autouse fixture in the shared `conftest.py`
  that stubs `telemetry_service.record_request_telemetry` to a no-op for
  every test **except** those in `tests/api/test_telemetry.py`, which
  exercises the real function directly and opts out via a filename check
  on `request.node.fspath`. This is a judgment call flagged for review —
  it's the standard way to isolate an unrelated cross-cutting side effect
  from tests that predate it, but it does mean `conftest.py` (shared
  infra, not itself a Task-N file) was touched outside the task's literal
  file list. No Task 1-4 test file content was modified.

## Design decisions / judgment calls

1. **`rollup_daily_latency` default date = today, not yesterday.** See
   above; documented in the docstring. Task 7 (docs) should note this when
   documenting the cron wiring: a nightly cron job must pass
   `target_date=<yesterday>` explicitly.
2. **`request_id` is not persisted.** Confirmed against
   `backend/migrations/050_account_administration.sql` — `request_telemetry`
   has no `request_id` column. `request.state.request_id` still gets set
   (for log/trace correlation, per the brief) but isn't written to any
   table.
3. **`conftest.py` autouse fixture** to stub telemetry recording for
   non-telemetry tests (see above) — flagging this explicitly since it's
   the one change outside the literal `backend/main.py` + new-files scope
   list, made necessary by the middleware change's cross-cutting effect on
   the shared `mock_db` connection used throughout the existing test suite.
4. **No new env vars introduced.** Task 7's docs task does NOT need to
   document any new `AUDIT_LOG_ROOT`-style env var for this task — retention
   windows (90 days / 1 year / 7 days) are hardcoded per the design spec,
   not configurable via env var, matching how the brief specified them.
   Task 7 should document: (a) `backend/scripts/purge_account_observability.py`
   as the retention command (`python -m backend.scripts.purge_account_observability`
   or `python backend/scripts/purge_account_observability.py`), and (b) that
   `rollup_daily_latency` exists but its cron/scheduling wiring is not yet
   built (explicitly out of scope for Task 5).

## Test commands run

```
D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/api/test_telemetry.py tests/unit/test_retention.py -v
```
Before implementation: 10 failed (5x `AttributeError: module 'services' has no attribute 'telemetry_service'`,
3x `ModuleNotFoundError: No module named 'scripts'`, 2x `ModuleNotFoundError: No module named 'services.telemetry_service'`)
— failed for the expected reason (modules didn't exist yet).

After implementation: **10 passed**.

```
D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/unit tests/api -v -m "not integration"
```
First run (before adding the `conftest.py` stub fixture): **175 passed, 6 failed** (all
6 pre-existing failures in `tests/api/test_auth.py`, all
`AssertionError: assert N+1 == N` on `conn.commit.call_count`, root-caused
to the new telemetry write sharing `mock_db`'s single mock connection).

After adding `_default_stub_telemetry` autouse fixture: **181 passed, 1 deselected** (the
Docker-gated schema test in `test_account_admin.py`, which self-skips
without Docker via its own `pytest.skip`, not the `-m "not integration"` filter — same deselection behavior as before this task).

## Open items / concerns for later tasks

- The `conftest.py` autouse fixture change (item 4 above) is the one part
  of this task that touched a file outside the literal scope list. It was
  necessary and minimal (one small fixture, zero changes to any existing
  test's assertions or logic), but flagging it explicitly per the task
  instructions in case a reviewer wants a different isolation strategy.
- `rollup_daily_latency`'s cron/scheduling wiring is explicitly out of
  scope per the brief ("that wiring/cron setup is out of scope for this
  task") — Task 7 or a later task should wire it up (e.g. a scheduled
  script or APScheduler job calling `rollup_daily_latency(target_date=yesterday)`
  once daily), and likewise wire `purge()` into a scheduled job or ops
  runbook.
- `purge_account_observability.py`'s `password_reset_tokens` purge is a
  bonus item per the brief's own note ("don't block DONE status on it if
  you run low on time") — it was completed and is covered by the general
  purge tests, but there's no dedicated retention-cutoff unit test
  specifically isolating it (the existing `test_retention.py` tests focus
  on the brief's named tables: `request_telemetry`, `account_audit_logs`,
  `user_sessions`, `endpoint_latency_daily`).
