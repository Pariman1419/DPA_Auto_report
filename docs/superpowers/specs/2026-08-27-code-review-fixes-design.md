# Design: Fix findings from code review (b6e3958..HEAD)

Date: 2026-08-27
Source: two-axis `/code-review` (Standards + Spec) run against the diff from
the initial commit (`b6e3958`) to the current working tree.

## Scope

Fix all 7 findings from the review:

1. Spec (c) — CR / Cross-Section Inspection count bug (real, still-broken bug)
2. Standards hard violation — `print()` instead of logger
3. Standards hard violation — path-translation logic duplicated 3x
4. Standards hard violation — missing rate limiting on sensitive endpoints
5. Standards hard violation — missing role/ownership gating on destructive endpoints
6. Standards smells — duplicated inline logger aliasing, hardcoded infra values, mysterious name (`_resolve_image_path` vs `_translate_image_path`)
7. Spec (b) — OpenTelemetry addition is undocumented scope creep → document it

Out of scope: everything else in the reviewed diff that wasn't flagged (e.g. general docker-compose changes beyond the OTEL network, the rest of the auth flow, frontend changes).

## 1. Bug fix — CR / Cross-Section Inspection count

**File:** `backend/services/product_request_service.py`

**Problem:** `docs/task.md` claims the "CR vs Cross Section Inspection" loose-matching bug is fixed. Only the display-assignment loop (line 455) actually excludes `CROSS`:

```python
if ("CR" in up_name or "C-R" in up_name) and "CROSS" not in up_name:
    f["fileCount"] = cr_valid_file_count
```

But `cr_valid_file_count` itself (lines 420-422) is computed without that exclusion:

```python
cr_valid_file_count  = next(
    (r[3] for r in raw_rows if "C-R" in r[0].upper() or "CR" in r[0].upper()), 0
)
```

and the SQL aggregate that produces `cr_valid_count` (lines 403-406) has the same gap:

```sql
COUNT(*) FILTER (
    WHERE (UPPER(category) LIKE '%%C-R%%' OR UPPER(category) LIKE '%%CR%%')
      AND image_seq IN ({cr_placeholders})
) AS cr_valid_count
```

Since `"CR"` is a substring of `"CROSS"`, both of these can match a `CROSS SECTION INSPECTION` row. Today it looks fine only because `GROUP BY category ORDER BY category` happens to sort `6.C-R` ahead of `CROSS SECTION INSPECTION` alphabetically, so `next()` picks the right row first — a fragile accident, not a fix.

**Fix:**
- SQL filter (line ~404): add `AND UPPER(category) NOT LIKE '%%CROSS%%'` to the `cr_valid_count` `FILTER` clause.
- `next()` lookup (line ~420-422): change the predicate to match the display loop's own exclusion: `("C-R" in r[0].upper() or "CR" in r[0].upper()) and "CROSS" not in r[0].upper()`.
- Add a regression test seeding both a `6.C-R` row and a `CROSS SECTION INSPECTION` row for the same `pr_no`/`timepoint`/`lot_name`, in an order where `CROSS...` sorts before `6.C-R` (or force it independent of alphabetical order), and assert `cr_valid_file_count` / `cr_valid_count` reflect only the true C-R row. Place under `tests/unit/` alongside the existing `test_path_translation.py` pattern.

## 2. Standards — `print()` instead of logger

**Files:** `backend/services/auth_service.py`, `backend/services/db_connector.py`

- `auth_service.py` currently has no logger import at all and uses `print(..., file=sys.stderr)` (line 10) before `sys.exit(1)`. Add `from logger import get_logger` and `log = get_logger("auth_service")` near the top, replace the `print()` with `log.error(...)`.
- `db_connector.py` already imports and configures `log = get_logger("db_connector")` (line 9), but `_require()` (line 18) still calls `print()` instead of using it. Replace with `log.error(...)`.
- Keep `sys.exit(1)` in both — this is intentional fail-fast startup behavior, only the reporting call changes.

## 3. Standards — path-translation triplication

**Files:** `backend/routers/product_request.py`, `backend/services/product_request_service.py`

- `product_request.py` defines its own `_resolve_image_path()` (lines 180-199), duplicating `_translate_image_path()` in `product_request_service.py` (lines 27-36) with a different name and a different return type (`pathlib.Path` vs `str`).
- Fix: delete `_resolve_image_path()` entirely. Import `_translate_image_path` from `services.product_request_service` and wrap its `str` result in `pathlib.Path(...)` at each of its two call sites (`download_report` line ~83, `get_image` line ~208), instead of keeping a second implementation.
- No other behavior changes — the two implementations already produce equivalent output (only formatting/type differ).

## 4. Standards — missing rate limiting

**File:** `backend/routers/product_request.py`, `backend/routers/auth.py`

Currently only `/login` (`auth.py`) and `/trigger-pipeline` (`3/minute`) are rate-limited. Add `@limiter.limit(...)` to:

| Endpoint | File | Limit |
|---|---|---|
| `POST /api/generate-report` | product_request.py | `3/minute` (heavy — builds a PPTX) |
| `GET /api/download-report` | product_request.py | `10/minute` |
| `POST /api/auth/register` | auth.py | `5/minute` (match `/login`) |
| `GET /api/auth/approve/{token}` | auth.py | `5/minute` |

Each handler needs the `Request` param added if not already present (required by `slowapi` for the limiter to key off the client address), following the existing pattern in `trigger_pipeline(request: Request, ...)`.

**`GET /api/image` — excluded from this list, revised assumption:** the initial draft proposed `30/minute` here, but `frontend/src/CreateReport.jsx` renders many `<img src="/api/image?...">` tags per page (preview grids with a "show more" past 10 images, plus SEM record galleries) — a single page view can legitimately fire well over 30 requests from one client in seconds, and multiple users behind the same office NAT would share that per-IP budget. A per-IP rate limit here would break normal gallery browsing, not just abuse. Leaving `/api/image` unlimited for now; its existing path-containment check (`is_relative_to(safe_root)`) is the actual protection CLAUDE.md calls for on file-serving endpoints. If abuse protection is wanted later, it should be a much higher ceiling (e.g. per-minute in the hundreds) or keyed by authenticated user rather than IP — a follow-up, not part of this fix.

## 5. Standards — role / ownership gating

**File:** `backend/routers/product_request.py`, `backend/routers/auth.py`

- `POST /api/trigger-pipeline`: change from `Depends(get_current_user)` to `Depends(require_role("admin"))` — this is a pure infra action (starts a docker-compose pipeline), no ownership concept applies, admin-only per your confirmation.
- `DELETE /api/history/{record_id}`: **not** role-only. Allow the delete if the caller is `admin`, OR the caller is the owner of that specific record (`report_generation_history.user_id`), matching your requirement "ลบได้เฉพาะ admin กับเจ้าของงาน". Implementation:

  ```python
  @router.delete("/history/{record_id}")
  def delete_history(record_id: int, user=Depends(get_current_user)):
      record = get_history_record(record_id)
      if not record:
          raise HTTPException(status_code=404, detail="Record not found")
      if user.get("role") != "admin" and record.get("user_id") != user.get("sub"):
          raise HTTPException(status_code=403, detail="Insufficient permissions")
      ok = delete_history_record(record_id, delete_file=True)
      if not ok:
          raise HTTPException(status_code=404, detail="Record not found")
      return {"status": "deleted"}
  ```

  Note: this fetches the record once for the ownership check and once inside `delete_history_record` — acceptable given low traffic on this endpoint; not worth restructuring `delete_history_record` to accept a pre-fetched record for a single call site.
  Note: `get_current_user()` returns the decoded JWT payload, whose user-id claim is `"sub"` (set at login in `auth.py:98-102`: `create_access_token({"sub": user["user_id"], "name": ..., "role": ...})`) — NOT `"userId"`. `record["user_id"]` (from `report_generation_history.user_id`, `VARCHAR(50)`) must be compared against `user["sub"]`.

  **Caveat (out of scope, flagged not fixed):** `report_generation_history.user_id` is written from `req.userId` — a client-supplied field in the `POST /generate-report` request body (`product_request.py:142`, `save_generation_history(..., user_id=req.userId, ...)`) — not derived server-side from the JWT `sub` claim at generation time. In normal use the frontend populates `req.userId` from the logged-in profile, so it lines up with `sub`, but nothing stops a client from sending a different `userId` when generating a report, which would let them "own" a history record under someone else's name for this new ownership check. This is a pre-existing gap unrelated to the 7 reviewed findings — not fixing it here, just noting it in case you want a follow-up to derive `user_id` server-side from the authenticated session instead of trusting the request body.

## 6. Standards — smells (low-risk cleanup)

- **Duplicated inline logger aliasing**: `product_request.py` currently does `from logger import get_logger as _gl` inline at 3 call sites (lines 130, 240, 250). Replace with one module-level `log = get_logger("product_request")` at the top of the file (same pattern as every other backend module), and use `log.info(...)` / `log.error(...)` at those call sites instead.
- **Hardcoded infra value**: `trigger_pipeline`'s docker-compose fallback (line 262) hardcodes `D:\Auto_detect\docker-compose.yml` with no override. (Correction from an earlier draft of this spec: the `localhost:9091` / `host.docker.internal:9091` URLs in `trigger_pipeline` and `pipeline_status` are NOT bare hardcodes — they're fallback defaults already overridable via existing `PIPELINE_TRIGGER_URL` / `PIPELINE_STATUS_URL` env vars, lines 226 and 281. Leave those as-is; only the compose path needs a new env var.) Add `PIPELINE_COMPOSE_PATH` (default `D:\Auto_detect\docker-compose.yml`), read once at module load, following the existing `DOC_ROOT`/`TEMPLATE_PATH`/`OUTPUT_DIR` convention.
- **Mysterious name**: resolved as a side effect of item 3 (the duplicate `_resolve_image_path` is deleted, so the naming collision goes away).

## 7. Spec doc catch-up — OpenTelemetry

**File:** `business_domain_requirements.md`

The diff adds `backend/opentelemetry_config.py`, wires `init_tracing()` into `main.py`, adds 5 `opentelemetry-*` packages to `requirements.txt`, and adds an `observability-net` external Docker network + OTEL env vars to `docker-compose.yml` — none of it traceable to any spec doc.

Add a new short section to `business_domain_requirements.md` (after the existing "ผู้ใช้งาน" / "ขั้นตอนการทำงานหลัก" sections) documenting:
- What it does: distributed tracing for the FastAPI backend, exported via OTLP.
- Why: operational visibility into request latency and errors across the report-generation pipeline (no existing requirement covered this — this is a new, accepted addition, being documented after the fact per team decision).
- New infra dependency: the backend now expects an `observability-net` external Docker network to exist (e.g. an OTEL collector / Jaeger stack) — document this as a deployment precondition, same as the existing `DB_HOST` precondition.

This is documentation-only — no code changes to the OTEL wiring itself, since the review found the implementation is functioning (best-effort: wrapped in `try/except: pass` in `main.py` so it fails open if the collector network doesn't exist).

## Testing

- New unit test for the CR/Cross-Section count fix (item 1), placed in `tests/unit/`.
- Manual smoke test: `DELETE /api/history/{id}` as a non-owner non-admin user → expect 403; as owner → expect 200; as admin on someone else's record → expect 200.
- Manual smoke test: `/api/trigger-pipeline` as non-admin → expect 403.
- No test changes needed for the logger/path-dedup/rate-limit/doc items — they're behavior-preserving refactors plus additive config, verified by existing test suite passing and manual endpoint checks (429 after exceeding the new rate limits).
