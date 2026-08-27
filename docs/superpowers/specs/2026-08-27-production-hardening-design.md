# Production Hardening Design

## Goal

Make Docker deployments reproducible, remove API-to-Docker privilege escalation in production, and make database/telemetry failures observable without leaking infrastructure detail.

## Scope

- Docker build context contains only tracked runtime assets.
- Pipeline trigger uses authenticated HTTP only in production.
- API errors return a request ID, not Docker/process details.
- PostgreSQL pool is initialized once at application lifecycle boundaries.
- Middleware records handled and unhandled HTTP outcomes without changing responses.

## Rules

- Production must reject Docker CLI fallback unless `ENABLE_PIPELINE_DOCKER_FALLBACK=true`.
- Never include command stderr, local paths, container names, tokens, headers, or query strings in client errors.
- Each image exposes the source commit through `APP_GIT_SHA`; health returns it only to authenticated admins or container inspection.
- Docker contexts must exclude `.git`, `.pnpm-store`, test artifacts, dev scripts, local environments, and untracked observability experiments.
- Database pool creation and closure are owned by FastAPI lifespan; request handlers only borrow/release connections.
- Telemetry is fail-open and must record 500 outcomes produced by unexpected handler exceptions.

## Acceptance

- A clean checkout builds identical runtime file sets and reports its commit SHA.
- Admin trigger succeeds through configured watcher HTTP endpoint; production never invokes Docker CLI.
- Trigger failure response contains a request ID but no infrastructure detail.
- Concurrent first requests do not create multiple connection pools.
- Tests cover all behavior above.
