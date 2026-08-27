# Production Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make DPA deployments reproducible and remove privileged Docker control from production API paths.

**Architecture:** Harden the Docker boundary first, then make request execution lifecycle-owned. `main.py` owns pool startup/shutdown and exception telemetry; the pipeline route only calls the watcher HTTP API in production.

**Tech Stack:** FastAPI, psycopg2, Docker Compose, React/Vite, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-production-hardening-design.md`

## Global Constraints

- No infrastructure details or secrets in HTTP errors. Client-facing responses must never contain command stderr, file paths, container names, tokens, headers, or query strings — a generic message plus a request ID only. Server-side logs are exempt from this restriction for non-secret infrastructure detail (container names, file paths, subprocess stderr) needed for ops debugging; logs must still never contain secrets (tokens, passwords, JWTs, DB credentials). (Clarified during Task 2 review: the plan owner confirmed logs may carry real diagnostic detail — resolves the PH-05 ambiguity in favor of the looser reading.)
- Production Docker CLI fallback requires an explicit true environment flag.
- All behavior changes use test-first verification.

---

## Test Cases (write before implementation)

| ID | Level | Scenario | Preconditions / Steps | Expected result |
| --- | --- | --- | --- | --- |
| PH-01a | API | Health stays public but hides build identity | Set `APP_GIT_SHA=abc123`; call `GET /health` with no auth | `200`; contains `status` only; no `gitSha`, no DB/JWT/token values |
| PH-01b | API | Health reveals build identity to admins only | Set `APP_GIT_SHA=abc123`; call `GET /health` authenticated as an admin | `200`; contains `status` and `gitSha=abc123`; no DB/JWT/token values |
| PH-01c | API | Health hides build identity from non-admins | Set `APP_GIT_SHA=abc123`; call `GET /health` authenticated as a non-admin user | `200`; contains `status` only; no `gitSha` |
| PH-02 | Build | Runtime image excludes local artifacts | Create a local `.pnpm-store/probe` and `backend/scripts/dev/probe.py`; build image; inspect filesystem | Neither probe exists in image |
| PH-03 | API | Production trigger never invokes Docker CLI | Unset `ENABLE_PIPELINE_DOCKER_FALLBACK`; force watcher HTTP failure; mock `subprocess.run` | `502/503`; `subprocess.run` not called; response contains request ID only |
| PH-04 | API | Development fallback is explicit | Set `ENABLE_PIPELINE_DOCKER_FALLBACK=true`; force watcher HTTP failure; mock Docker restart success | `200`; Docker command called with fixed allowlisted args |
| PH-05 | API | Trigger error is sanitized | Force Docker/HTTP error containing `/srv/compose.yml` and container name | Response excludes both strings; server log contains request ID and sanitized failure category |
| PH-06 | Unit | Pool initialization is singleton | Call `initialize_dpa_pool()` concurrently from two threads with mocked pool constructor | constructor called once; both callers receive same pool |
| PH-07 | Lifecycle | Pool closes on shutdown | Start FastAPI lifespan then exit it with mocked pool | `closeall()` called exactly once |
| PH-08 | API | Unhandled failure retains telemetry | Route raises `RuntimeError`; mock telemetry writer | `500`; response contains request ID; telemetry called once with status `500` and templated route |
| PH-09 | Security | Sensitive reset URL remains redacted on 500 | Route `/api/auth/reset-password/raw-secret` raises | Logs/telemetry contain `/api/auth/reset-password/{token}`, never `raw-secret` |
| PH-10 | Regression | Default suite is deterministic | Run `python -m pytest -q` from clean checkout | API/unit/integration/performance/regression tiers pass; E2E remains an explicit separate invocation |


### Task 1: Deterministic Docker images

**Files:** Modify `.dockerignore`, `backend/.dockerignore`, `docker-compose.yml`, `backend/main.py`; test `tests/api/test_health.py`.

- [ ] Write failing tests asserting `/health` exposes no secret to anyone, and reports a configured `APP_GIT_SHA` only when the caller is authenticated as admin (PH-01a/b/c).
- [ ] Add `ARG APP_GIT_SHA` and `ENV APP_GIT_SHA`; pass `GIT_SHA` from Compose build args.
- [ ] Exclude development/store/test artifacts from every Docker context and ensure runtime source is tracked.
- [ ] Run `docker compose build --no-cache` and inspect image labels/environment.
- [ ] Commit: `git commit -m "build: make runtime images reproducible"`.

### Task 2: Restrict pipeline execution boundary

**Files:** Modify `backend/routers/product_request.py`, `backend/models/schemas.py`; test `tests/api/test_product_request.py`.

- [ ] Write failing tests: production trigger failure never calls `subprocess.run`; development fallback requires `ENABLE_PIPELINE_DOCKER_FALLBACK=true`.
- [ ] Make watcher HTTP trigger the default and only path in production.
- [ ] Return `{detail: "Pipeline trigger failed", requestId}` while logging sanitized diagnostic context server-side.
- [ ] Run the focused tests and then `python -m pytest`.
- [ ] Commit: `git commit -m "fix: isolate pipeline trigger from Docker CLI"`.

### Task 3: Own database pool lifecycle

**Files:** Modify `backend/main.py`, `backend/services/db_connector.py`; test `tests/unit/test_db_connector.py`.

- [ ] Write failing tests for one-time pool initialization and pool close on application shutdown.
- [ ] Add `initialize_dpa_pool()` and `close_dpa_pool()` guarded by a module lock.
- [ ] Register FastAPI lifespan to initialize/close the pool; retain borrow/release API for services.
- [ ] Run database unit tests and API smoke tests.
- [ ] Commit: `git commit -m "refactor: manage database pool through app lifespan"`.

### Task 4: Exception-safe request telemetry

**Files:** Modify `backend/main.py`, `backend/services/telemetry_service.py`; test `tests/api/test_telemetry.py`.

- [ ] Write failing test that an endpoint raising an unexpected exception yields a sanitized 500 response and one telemetry record with status 500.
- [ ] Wrap middleware dispatch in `try/except/finally`; preserve existing response behavior and fail-open telemetry.
- [ ] Ensure request IDs are attached to error responses and logs without raw URL secrets.
- [ ] Run telemetry and full pytest suite.
- [ ] Commit: `git commit -m "fix: record telemetry for unhandled failures"`.

### Task 5: Deployment verification and documentation

**Files:** Modify `README.md`, `BACKEND_CONTRACT.md`; test all suites.

- [ ] Document `APP_GIT_SHA`, `ENABLE_PIPELINE_DOCKER_FALLBACK`, health semantics, and rebuild procedure.
- [ ] Run `python -m pytest`, `pnpm.cmd build`, `docker compose config --quiet`, and `docker compose up -d --build`.
- [ ] Verify `docker compose ps`, backend health, and frontend HTTP response.
- [ ] Commit: `git commit -m "docs: document production hardening operations"`.
