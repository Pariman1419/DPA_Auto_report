# Task 1 Report: Deterministic Docker images

(This file previously held a report for an unrelated "account administration &
observability schema" task — a leftover from a different plan run in this same
worktree. It has been overwritten with the correct report for the actual
Task 1 of `docs/superpowers/plans/2026-08-27-production-hardening.md`,
"Deterministic Docker images".)

## What was implemented

**`GET /health` now reports build identity (PH-01).** `backend/main.py`:

```python
@app.get("/health")
def health():
    return {"status": "ok", "gitSha": os.getenv("APP_GIT_SHA", "unknown")}
```

**Ambiguity resolved — flagging per instructions.** The task brief pointed
out a tension between the plan's global constraint ("health returns it only
to authenticated admins or container inspection") and PH-01's literal test
steps (unauthenticated `GET /health`, expects `gitSha` in the body). I
resolved this in favor of PH-01: `/health` stays fully unauthenticated (an
existing test, `tests/api/test_telemetry.py::test_health_check_records_nothing`,
already calls it with no auth headers and expects `200`, and the router
middleware explicitly special-cases `/health` to skip telemetry). `gitSha`
is a commit hash, not a secret, and the endpoint still contains no DB/JWT/
token values (asserted by the new test). The "admins/container inspection"
language most plausibly refers to *other*, more detailed build/infra
metadata that isn't part of this task's scope — no such field was added, so
nothing sensitive is exposed either way. Noting this as a resolved judgment
call rather than a blocking question, per the task's own steer: "don't break
[unauthenticated] with an auth requirement unless the spec is asking you to
gate the gitSha field specifically."

**Docker build-arg plumbing.** Both `backend/Dockerfile` and
`frontend/Dockerfile` gained:

```dockerfile
ARG APP_GIT_SHA=unknown
ENV APP_GIT_SHA=${APP_GIT_SHA}
LABEL org.opencontainers.image.revision=${APP_GIT_SHA}
```

`docker-compose.yml` passes it through from a `GIT_SHA` host env var (falls
back to `unknown` if unset) via `build.args` on both `backend` and
`frontend` services. The task's Files list only named `backend/main.py`
among application files, but "expose the source commit through
`APP_GIT_SHA`" and "each image" (plural, per the design doc) necessarily
means touching both Dockerfiles — there's nowhere else `ARG`/`ENV` can live.
I added the same treatment to the frontend image for consistency (its own
`APP_GIT_SHA` env + OCI revision label), even though frontend doesn't serve
a `/health`-style endpoint — it's an nginx static server, so this is passive
metadata only (`docker inspect`/`docker exec env`).

**`.dockerignore` hardening (PH-02).** Root `.dockerignore` (new file) and
`frontend/.dockerignore` now exclude `.git/` and `.pnpm-store/`;
`backend/.dockerignore` now excludes `.git/`, `.env.*`, `scripts/dev/`,
`logs/`, and `*.log`, in addition to what was already there
(`test_*.py`, `__pycache__/`, etc.). `backend/scripts/dev/` is a new dev-only
subdirectory (didn't exist before this task; the probe path
`backend/scripts/dev/probe.py` is fictional per PH-02, used only to verify
exclusion) — excluding it protects any future dev scripts placed there
without touching the real `backend/scripts/purge_account_observability.py`.
`logs/*.log` exclusion is safe because `backend/logger.py` creates
`logs/` at runtime via `os.makedirs(LOG_DIR, exist_ok=True)` — nothing
requires the directory to pre-exist in the image.

Root `.dockerignore` is added as defense-in-depth even though neither
service's build context is currently the repo root (`docker-compose.yml`
uses `./backend` and `./frontend`) — it only bites if someone later builds
with `-f backend/Dockerfile .` from root, but the task's Files list
explicitly named it, and the design doc's global constraint ("Docker
contexts must exclude `.git`, `.pnpm-store`, test artifacts, dev scripts,
local environments...") reads as should-hold-everywhere.

## What was tested

### TDD Evidence

**RED** — wrote `tests/api/test_health.py` with
`test_health_reports_configured_git_sha` (sets `APP_GIT_SHA=abc123` via
`monkeypatch.setenv`, asserts `body["gitSha"] == "abc123"`) before touching
`main.py`. Ran:

```
cd tests && D:/DPA/backend/venv/Scripts/python.exe -m pytest api/test_health.py -v
```

Result: `test_health_reports_configured_git_sha FAILED — KeyError: 'gitSha'`
(the second test, `test_health_exposes_no_secret_values`, passed
incidentally since the old `{"status": "ok"}` body trivially satisfies "no
secrets" — expected, since that assertion isn't what changed). This
confirmed the failure was for the right reason: the field didn't exist yet.

**GREEN** — after adding `"gitSha": os.getenv("APP_GIT_SHA", "unknown")` to
`backend/main.py`'s `health()`:

```
cd tests && D:/DPA/backend/venv/Scripts/python.exe -m pytest api/test_health.py -v
```

Result: `2 passed in 0.51s`.

### Full suite

```
cd tests && D:/DPA/backend/venv/Scripts/python.exe -m pytest -q
```

Result: `196 passed in 6.38s` (baseline was 194; +2 for the new
`test_health.py` file). No failures, no new warnings beyond the pre-existing
`pytest_asyncio` deprecation notice (unrelated to this change, present in
the baseline run too).

### Docker build + inspection (PH-02)

Created probe artifacts in every location a leak could plausibly occur, then
removed them after verification (not committed):
- `.pnpm-store/probe` (repo root, per PH-02's literal wording)
- `frontend/.pnpm-store/probe` (inside the frontend build context, where a
  local pnpm store would realistically land)
- `backend/scripts/dev/probe.py` (inside the backend build context)

Built both images from scratch:

```
GIT_SHA=$(git rev-parse --short HEAD) docker compose build --no-cache backend frontend
```

Both built successfully (`Image dpa-frontend:latest Built`,
`Image dpa-backend:latest Built`).

Inspected:

```
docker run --rm dpa-backend:latest find /app -iname "*probe*" -o -iname "*pnpm*"
  → (no output — nothing found)
docker run --rm dpa-frontend:latest find / -xdev -iname "*probe*" -o -iname "*pnpm*"
  → /usr/sbin/partprobe, /sbin/modprobe, /etc/modprobe.d
  (unrelated pre-existing nginx:alpine system binaries, not our probes)

docker run --rm dpa-backend:latest env | grep APP_GIT_SHA
  → APP_GIT_SHA=72eff33

docker image inspect dpa-backend:latest --format '{{json .Config.Labels}}'
  → {"org.opencontainers.image.revision":"72eff33", ...compose labels...}
docker image inspect dpa-frontend:latest --format '{{json .Config.Env}}'
  → [...,"APP_GIT_SHA=72eff33"]
docker image inspect dpa-frontend:latest --format '{{json .Config.Labels}}'
  → {"org.opencontainers.image.revision":"72eff33", ...}
```

`72eff33` is the worktree's base commit (`git rev-parse --short HEAD` at
build time) — confirms the build-arg plumbing works end to end. No probe or
`.pnpm-store` content leaked into either image.

`docker compose config --quiet` fails in this worktree, but for an unrelated
pre-existing reason: `backend/.env` doesn't exist in this worktree checkout
(it's gitignored and was never created here). This is not something Task 1
introduced or is responsible for fixing — `docker compose build` (the
command this task actually calls for) succeeded fine since building doesn't
consult `env_file`. Did not run `docker compose up` per the task's explicit
instruction not to redeploy production containers.

## Files changed

- `backend/main.py` — `/health` now returns `gitSha`.
- `backend/Dockerfile` — `ARG`/`ENV`/`LABEL` for `APP_GIT_SHA`.
- `frontend/Dockerfile` — same, for consistency across "each image."
- `docker-compose.yml` — `build.args.APP_GIT_SHA: ${GIT_SHA:-unknown}` on
  both services.
- `.dockerignore` (new) — root-level defense-in-depth exclusions.
- `backend/.dockerignore` — added `.git/`, `.env.*`, `scripts/dev/`,
  `logs/`, `*.log`.
- `frontend/.dockerignore` — added `.git/`, `.pnpm-store/`.
- `tests/api/test_health.py` (new) — PH-01 coverage.

## Self-review

- Followed TDD: failing test written and run before the implementation
  change.
- Didn't touch `docker-compose.yml`'s `environment:` block for
  `APP_GIT_SHA` — it doesn't need to be there since the `ENV` baked in at
  build time already sets it in the image, and `docker-compose.yml`'s
  existing `environment:` overrides in this file are reserved for
  runtime-configurable values (paths, CORS origins), not build-time
  identity. Confirmed via `docker run --rm dpa-backend:latest env` that the
  value is present without any runtime environment override.
- Considered whether to add `logs/` exclusion was in-scope — it's not named
  in the task's Files list or PH-02, but it's a "local environment"-shaped
  artifact per the global constraint prose, and removing it is risk-free
  (confirmed the app recreates the directory at runtime). Flagging as a
  minor scope extension in case the plan owner disagrees.
- Did not modify `backend/scripts/purge_account_observability.py` or
  `backend/scripts/__init__.py` — only the new `scripts/dev/` subtree is
  excluded, keeping the real ops script in the image.
- Test file follows the existing pytest conventions in `tests/api/` (uses
  the shared `client` fixture from `tests/conftest.py`, `@pytest.mark.api`
  marker, `monkeypatch.setenv` for isolation rather than mutating
  `os.environ` directly).

## Concerns

- The auth-vs-unauthenticated ambiguity for `gitSha` (see above) was
  resolved by judgment rather than by asking a human, since Auto Mode was
  active for this run and the task brief itself pointed toward PH-01's
  literal unauthenticated test as the more concrete source of truth. If the
  intent really was "gate `gitSha` behind admin auth," that would be a
  follow-up change to `/health` (splitting a public liveness response from
  an authenticated diagnostic one) — flagging for the plan owner to confirm
  either way.
- `docker compose config --quiet` cannot run cleanly in this worktree due to
  a missing `backend/.env` (pre-existing, unrelated to this task — no
  `.env` file exists anywhere in this checkout). `docker compose build`
  (what the task explicitly asks for) is unaffected and succeeded.
- `.superpowers/sdd/task-1-report.md`, `task-3-report.md`, and
  `task-5-report.md` already existed in this worktree before I started, and
  contained reports for a *different* plan (account-administration schema
  work referencing Tasks 1/3/5 of a different numbering). I overwrote only
  `task-1-report.md` with this task's real report, per my brief. I did not
  touch `task-3-report.md` / `task-5-report.md` — they're stale leftovers
  from whatever ran in this worktree before, not something in my task's
  scope to clean up, but worth the plan owner's attention since they could
  be misread as this plan's actual Task 3/5 status.

## Commit

```
git add .dockerignore backend/.dockerignore frontend/.dockerignore backend/Dockerfile frontend/Dockerfile docker-compose.yml backend/main.py tests/api/test_health.py
git commit -m "build: make runtime images reproducible"
```

Result: `cb4a4e8 build: make runtime images reproducible` (8 files changed,
94 insertions, 1 deletion).

## Fix: gate gitSha behind admin auth

### What was implemented

`GET /health` (backend/main.py) stays fully public and DB-independent, always
returning `{"status": "ok"}`. The `gitSha` field (sourced from `APP_GIT_SHA`)
is now only included when the request carries a valid JWT (from the
`dpa_token` cookie or `Authorization: Bearer` header) whose decoded payload
has `role == "admin"`. Decoding is wrapped in try/except so a missing,
malformed, or expired token never raises -- it's treated as "not admin" and
`gitSha` is simply omitted. No database lookup is performed (mirrors how
`get_current_user` treats tokens without the `sv` claim as valid without a DB
round-trip), keeping `/health` usable as an infrastructure liveness/readiness
probe.

Test file `tests/api/test_health.py` was rewritten to cover PH-01a/b/c from
the plan (previously it asserted the old fully-public gitSha behavior).

### RED

```
cd D:\DPA\.claude\worktrees\production-hardening\tests
D:\DPA\backend\venv\Scripts\python.exe -m pytest api/test_health.py -q
```

Result (against the old public-gitSha implementation):
```
api\test_health.py F.F.                                                  [100%]
FAILED api/test_health.py::test_health_unauthenticated_has_no_git_sha - AssertionError: assert 'gitSha' not in {'gitSha': 'abc123', 'status': 'ok'}
FAILED api/test_health.py::test_health_non_admin_has_no_git_sha - AssertionError: assert 'gitSha' not in {'gitSha': 'abc123', 'status': 'ok'}
2 failed, 2 passed in 0.52s
```

### GREEN

```
cd D:\DPA\.claude\worktrees\production-hardening\tests
D:\DPA\backend\venv\Scripts\python.exe -m pytest api/test_health.py -q
```

Result:
```
api\test_health.py ....                                                  [100%]
4 passed in 0.80s
```

### Full suite

```
cd D:\DPA\.claude\worktrees\production-hardening\tests
D:\DPA\backend\venv\Scripts\python.exe -m pytest -q
```

Result: `198 passed in 10.69s` (baseline before this fix was 196; net +2 from
splitting the old 2-test file into 4 tests covering PH-01a/b/c plus the
secret-leak check). No regressions.

### Files changed

- `backend/main.py` -- `/health` now gates `gitSha` on admin JWT role
- `tests/api/test_health.py` -- rewritten to cover PH-01a/PH-01b/PH-01c

### Concerns

None. The change only touches `/health`'s response construction; the
`.dockerignore`/`Dockerfile`/`docker-compose.yml` parts of Task 1's original
commit (`cb4a4e8`) were untouched.
