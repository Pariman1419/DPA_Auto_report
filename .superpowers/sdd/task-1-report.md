# Task 1 Report: Account-administration & observability schema

## Summary

Created `backend/migrations/050_account_administration.sql` (new `backend/migrations/`
directory) and mirrored the same additions in `schema.sql`, so a fresh install and a
migrated install converge on the same schema. Also fixed one genuine defect found in
the pre-existing test file (see below). No service/router code was touched, per scope.

## What was built

`backend/migrations/050_account_administration.sql` (idempotent, uses
`ADD COLUMN IF NOT EXISTS` / `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`
throughout):

- `users` — adds `account_status VARCHAR(20) NOT NULL DEFAULT 'active'` and
  `session_version INTEGER NOT NULL DEFAULT 1`.
- `account_audit_logs` — `id, actor_user_id, target_user_id, action, before_state
  JSONB, after_state JSONB, occurred_at TIMESTAMPTZ`. Index:
  `(target_user_id, occurred_at DESC)`.
- `user_sessions` — `id, user_id, ip_address, user_agent, created_at TIMESTAMPTZ,
  expires_at TIMESTAMPTZ, revoked_at TIMESTAMPTZ`. Index: `(user_id, created_at DESC)`.
- `request_telemetry` — `id, user_id, route, method, status_code, duration_ms,
  occurred_at TIMESTAMPTZ`. Indexes: `(user_id, occurred_at DESC)` and
  `(route, occurred_at DESC)`. Deliberately excludes body/query-string/header
  columns per the "never persist" constraint.
- `endpoint_latency_daily` — daily rollup per route/day (`request_count,
  error_count, avg_latency_ms, p95_latency_ms, max_latency_ms, created_at
  TIMESTAMPTZ, updated_at TIMESTAMPTZ`), `UNIQUE (route, day)`.
- `password_reset_tokens` — `id, user_id, token_hash VARCHAR(128), created_at
  TIMESTAMPTZ, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ`. Only stores
  a hash — no `token`/`raw_token` column. `UNIQUE (token_hash)`.

Every new table has an indexed `TIMESTAMPTZ` column so Task 5's retention pruning
(90 days for `request_telemetry`, 1 year elsewhere) has an index to work against.

`schema.sql` received the identical block (inserted before the "Seed Data" section,
right after the existing tables) so `CREATE TABLE IF NOT EXISTS` on a fresh DB and
the migration on an existing DB produce the same result.

## Defect found and fixed in the existing test

`tests/api/test_account_admin.py` line 144 used:

```sql
AND column_name LIKE '%at%'
```

intending to select timestamp-like columns (`created_at`, `occurred_at`, etc.) for
the "must be TIMESTAMPTZ" assertion. But `LIKE '%at%'` matches the substring `at`
*anywhere* in the name — and `before_state` / `after_state` contain `at` (from
"st**at**e"), as does e.g. `status_code`/`account_status`. Since the same test also
asserts `before_state`/`after_state` are `jsonb` (lines 156-158), the test as
originally written was internally contradictory: no valid schema could satisfy both
assertions simultaneously.

I confirmed this with a quick Python substring check (`'at' in 'before_state'` →
`True`) before writing any table DDL, rather than contorting column names to dodge
the bug.

Fix: changed the filter to `column_name ~ '_at$'` (columns *ending* in `_at`),
which is the actual naming convention already used across the codebase
(`created_at`, `occurred_at`, `expires_at`, `used_at`, `revoked_at`) and correctly
excludes `before_state`/`after_state`/`status_code`/`account_status`. This is a
one-line change (`tests/api/test_account_admin.py` line 144) — no other part of the
test was touched.

## Commands run and results

1. First run (expected failure — no migration file yet):
   ```
   D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/api/test_account_admin.py -v
   ```
   Result: `FAILED` — `FileNotFoundError: ... backend\migrations\050_account_administration.sql`
   (exit code 1). Confirms the test fails for the right reason before any schema work.

2. After writing the migration + `schema.sql` + the test fix, re-ran the same command:
   ```
   D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/api/test_account_admin.py -v
   ```
   Result: `1 passed in 2.11s` (exit code 0). The test itself applies `schema.sql`
   then the migration file twice inside a disposable `postgres:16` Docker container
   on port 55432, so this single green run already proves double-apply idempotency.

3. Re-ran once more from a clean container to confirm stability:
   ```
   D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/api/test_account_admin.py -v
   ```
   Result: `1 passed in 2.06s` (exit code 0).

## Self-review

- `git diff schema.sql` shows exactly the mirrored block, byte-identical in
  structure to the migration file's DDL (see diff captured during the session).
- `backend/migrations/` did not exist before this task; `050_account_administration.sql`
  is the first file in it, as instructed.
- No `backend/main.py`, service, or router files were touched.
- All timestamp columns use `TIMESTAMPTZ`; none use bare `TIMESTAMP`.
- No SQL is built via string formatting — the migration is a static file; no helper
  script was written to run it (the test applies it directly via psycopg2 `cur.execute`
  with no interpolation).
- `password_reset_tokens` has `token_hash` only, verified by the test's explicit
  `assert "token" not in reset_cols` / `assert "raw_token" not in reset_cols`.

## Concerns

- The one-line test fix (`LIKE '%at%'` → `~ '_at$'`) is a change to a file the
  instructions describe as "complete and good quality" and said not to rewrite
  "unless you find a genuine defect." I judged this qualifies: the original
  assertion was unsatisfiable by any schema meeting the brief's own requirement
  that `before_state`/`after_state` be JSONB, so it was not a matter of my table
  design choices — any correct implementation would have hit this. Flagging for
  visibility in case the plan owner wants to double check.
- Column/table design choices beyond the names mandated by the brief and test
  (e.g. `id` as `BIGSERIAL`, `route VARCHAR(200)`, `ip_address`/`user_agent` on
  `user_sessions`, the `endpoint_latency_daily` rollup shape) were my own
  reasonable inference from "observability" intent — later tasks (2 and 4) may
  need additional columns on these tables that I did not anticipate. I kept
  every table minimal but plausible, and all mandated names/types match the
  brief and test exactly.

## Commit

Committed per the brief's exact instruction:

```
git add backend/migrations/050_account_administration.sql schema.sql tests/api/test_account_admin.py
git commit -m "feat: add account administration schema"
```

## Fix Wave 1

Addressed two Important review findings and one Minor finding against the migration and its test.

### Finding 1 — missing index on `account_audit_logs.actor_user_id`

Added `idx_account_audit_logs_actor_occurred ON account_audit_logs (actor_user_id, occurred_at DESC)`
alongside the existing `idx_account_audit_logs_target_occurred`, in both
`backend/migrations/050_account_administration.sql` and the mirrored block in `schema.sql`.
This supports "actions taken by admin X" audit queries per the plan's global index constraints.

### Finding 2 — `user_sessions` index didn't match plan wording

Renamed `user_sessions.created_at` to `started_at` (reads more consistently alongside
`expires_at`/`revoked_at` as "when did this session start"), rather than adding a second
overlapping index. Changes:

- `schema.sql` (fresh-install path): column declared as `started_at TIMESTAMPTZ` directly;
  no rename needed since `CREATE TABLE IF NOT EXISTS` only ever runs once on a fresh DB.
- `backend/migrations/050_account_administration.sql`: `CREATE TABLE IF NOT EXISTS` now
  declares `started_at` directly (for a genuinely fresh DB), and an idempotent
  `DO $$ ... IF EXISTS (... column_name = 'created_at') THEN ALTER TABLE user_sessions
  RENAME COLUMN created_at TO started_at; END IF; END $$;` block handles the case where the
  table already exists from a prior run with the old column name. The old
  `idx_user_sessions_user_created` index is dropped (`DROP INDEX IF EXISTS`) and replaced
  with `idx_user_sessions_user_started ON user_sessions (user_id, started_at DESC)` — this
  avoids ending up with two overlapping indexes covering the same column after a rename.
- No backend service/router code referenced `user_sessions.created_at` yet (grepped the
  whole worktree — only schema.sql, the migration, the test, and docs mention
  `user_sessions`), so no other file needed updating.

### Finding 3 — index assertions checked concatenated indexdefs, not per-table

`tests/api/test_account_admin.py::test_account_admin_schema` previously joined ALL
`pg_indexes.indexdef` rows (across every table) into one string and substring-matched
against it — meaning an index with the right shape on the *wrong* table would have
satisfied the assertion. This is exactly how Findings 1 and 2 slipped through the first
review pass. Replaced the single concatenated check with a per-table helper
(`_indexdefs_for(table_name)` querying `pg_indexes` filtered by `tablename`) and separate
assertions against `account_audit_logs` (both target_user_id and actor_user_id indexes),
`user_sessions` (user_id + started_at), and `request_telemetry` (user_id + occurred_at,
route + occurred_at) — each assertion now names its table in the failure message.

### Command run

```
D:/DPA/backend/venv/Scripts/python.exe -m pytest tests/api/test_account_admin.py -v
```

Output (tail):
```
tests\api\test_account_admin.py::test_account_admin_schema PASSED        [100%]
============================== 1 passed in 2.10s ==============================
```

Exit code: 0.
