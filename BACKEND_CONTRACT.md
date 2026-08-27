# Backend API Contract — DPA QA Report System

Base URL: `http://localhost:9090`  
Auth: `httpOnly` Cookie `dpa_token` (primary) | `Authorization: Bearer <token>` (fallback)  
All endpoints require authentication unless marked **[public]**

---

## Auth — `/api/auth`

### POST /api/auth/login **[public]** **[rate: 5/min]**
```json
// Request
{ "userId": "EMP001", "password": "secret" }

// Response 200
{
  "access_token": "<jwt>",
  "token_type": "bearer",
  "user": { "userId": "EMP001", "fullName": "John Doe", "role": "QA Engineer" }
}
// Set-Cookie: dpa_token=<jwt>; HttpOnly; SameSite=Lax; Path=/

// Error 401 — invalid credentials
// Error 503 — DB unavailable
```

### POST /api/auth/logout
```json
// Response 200
{ "status": "ok" }
// Clears dpa_token cookie
```

### POST /api/auth/register **[public]** **[rate: 5/min]**
```json
// Request
{
  "userId": "EMP002",
  "fullName": "Jane Smith",
  "password": "secret",
  "email": "jane@example.com"   // optional
}

// Response 200
{ "status": "success", "message": "Account created. Please wait for admin approval." }

// Error 409 — Employee ID already registered
// Error 503 — DB unavailable
```

### GET /api/auth/approve/{token} **[admin, QA Engineer only]** **[rate: 5/min]**
```
// token — signed itsdangerous token (24h expiry) from approval email

// Response 200
{ "message": "User EMP002 has been approved and activated." }

// Error 400 — expired or invalid token
// Error 404 — user not found
```

### POST /api/auth/reset-password/{token} **[public]** **[rate: 5/min]**
```
// token — raw one-time reset token from a link issued by
// POST /api/admin/accounts/{user_id}/reset-link (shown once in the admin UI,
// never emailed). Looked up by SHA-256 hash in password_reset_tokens; a
// DIFFERENT mechanism from the itsdangerous approval-link token above.

// Request
{ "password": "newSecret123" }

// Response 200
{ "message": "Password has been reset." }

// Error 400 — link invalid, expired (30 min TTL), or already used (generic
//              message either way, to avoid leaking which case it was)
```
On success: password is updated, `users.session_version` is incremented
(invalidating every JWT issued before the reset, since protected routes
compare the token's `sv` claim against the live DB value — see Auth flow
below), and the action is written to `account_audit_logs`.

**Session invalidation (`sv` claim):** every login mints a JWT carrying
`sv: session_version` at issue time. Tokens minted before this claim existed
(no `sv`) are honored exactly as before — no DB lookup. Tokens carrying `sv`
are compared against the live `users.session_version` on every protected
request; a mismatch (e.g. after a reset-triggered bump) or a DB outage during
the check both fail closed with 401, since this is an authentication gate,
not a best-effort telemetry write.

---

## Product Requests — `/api`

### GET /api/product-requests
```json
// Response 200 — array
[
  { "productRequestNo": "PR2024001", "folderName": "PR2024001", "hasExcel": true }
]
```

### GET /api/product-request/{pr_number}
```json
// Response 200
{
  "productRequestNo": "PR2024001",
  "folderName": "PR2024001",
  "subject": "DPA for MT0 package",
  "purpose": "Reliability evaluation",
  "date": "2024-01-15",
  "conclusion": "",
  "summary": {},
  "backgroundInfo": {
    "customerName": "MT0",
    "assemblySite": "Hana",
    "packageType": "QFN",
    "dateCode": "2401",
    "packageSize": "5x5",
    "numberOfLot": "1",
    "pinBallCount": "32",
    "requestorNameDept": "QA Dept",
    "reliabilityStaffName": "Staff A",
    "relRequestNumber": ""
  },
  "billOfMaterial": {
    "orderLot": "MTDQS0906.1",
    "custAssy": "MT0-QFN32",
    "device": "MT001",
    "dieSize": "3x3",
    "dapSize": "3.1x3.1",
    "lfStockNo": "LF001",
    "dieAttachMaterial": "DAM-X",
    "wireType": "Au 25um",
    "moldCompound": "MC-A",
    "platingFinish": "NiPdAu"
  },
  "reliabilityTests": [
    {
      "name": "HTSL",
      "duration": "168h",
      "condition": "150°C",
      "sampleSize": "77",
      "status": "Pass",
      "planStart": null,
      "planFinish": null,
      "steps": []
    }
  ],
  "dpaItems": []
}

// Error 404 — PR not found
// Error 422 — invalid data
// Error 500 — fetch failed
```

### GET /api/product-request/{pr_number}/lots
```json
// Response 200
["MTDQS0906.1", "MTDQS0907.2"]
```

### GET /api/product-request/{pr_number}/lots-registry
```json
// Response 200
{
  "MTDQS0906.1": ["T0", "T168", "T500"],
  "MTDQS0907.2": ["T0", "T168"]
}
```

### GET /api/product-request/{pr_number}/timepoints?lot={lot}
```json
// Response 200
["T0", "T168", "T500"]
```

### GET /api/product-request/{pr_number}/{timepoint}/folders?lot={lot}
```json
// Response 200 — sorted by category priority (EXTERNAL=1 ... BS,WP,SP=7)
[
  { "name": "1.EXTERNAL VISUAL", "fileCount": 20 },
  { "name": "2.DELAM",           "fileCount": 5  },
  { "name": "3.X-RAY",           "fileCount": 8  },
  { "name": "4.DECAP",           "fileCount": 12 },
  { "name": "5.IMC",             "fileCount": 25, "imcCount": 25 },
  { "name": "6.C-R",             "fileCount": 6,  "semCount": 4  },
  { "name": "7.BS,WP,SP",        "fileCount": 0,  "hasBondAbility": true, "bondCount": 3 }
]
```

### GET /api/product-request/{pr_number}/{timepoint}/next-revision
```json
// Response 200
{ "nextRevision": "A" }
```

---

## Preview Endpoints

### GET /api/product-request/{pr_number}/{timepoint}/{lot}/preview-images?category={cat}
```json
// Response 200
[
  { "fileName": "IMG001.jpg", "filePath": "D:\\Auto_detect\\Result\\...\\IMG001.jpg", "imageSeq": "1-1" }
]
```

### GET /api/product-request/{pr_number}/{timepoint}/{lot}/preview-imc
```json
// Response 200
[
  { "unitId": "1-1", "value": 93.35 },
  { "unitId": "1-2", "value": 91.20 }
]
```

### GET /api/product-request/{pr_number}/{timepoint}/{lot}/preview-bond
```json
// Response 200
[
  { "testType": "Ball Shear", "unitId": "1", "force": 45.2, "grade": "A", "type": "Normal" }
]
```

### GET /api/product-request/{pr_number}/{timepoint}/{lot}/preview-sem
```json
// Response 200
[
  {
    "unitId": "1", "pointId": "1",
    "magnification": "5000x", "accelVolt": "15kV",
    "filePath": "D:\\Auto_detect\\Result\\...\\sem.jpg",
    "fileName": "sem.jpg"
  }
]
```

---

## Report Generation

### POST /api/generate-report **[rate: 3/min]**
```json
// Request
{
  "prNumber": "PR2024001",
  "timepoint": "T0",
  "lot": "MTDQS0906.1",
  "selectedSections": {
    "EXTERNAL VISUAL": true,
    "DELAM": false,
    "X-RAY": true,
    "DECAP": true,
    "IMC": true,
    "C-R": false,
    "BS,WP,SP": false
  },
  "userId": "EMP001",
  "revision": "A"
}

// Response 200
{
  "status": "success",
  "revision": "A",
  "outputPath": "D:\\DPA\\output\\DPA_Report_PR2024001_T0_MTDQS0906.1_20240115_103045.pptx",
  "filename": "DPA_Report_PR2024001_T0_MTDQS0906.1_20240115_103045.pptx",
  "stats": {
    "metadata_found": true,
    "images_found": 45,
    "images_missing": 2,
    "total_slides": 18,
    "missing_list": ["EXTERNAL_21", "XRAY_9"]
  }
}

// Error 500 — generation failed (detail contains error message)
```

---

## Pipeline Integration

### POST /api/trigger-pipeline **[admin]** **[rate: 3/min]**
```json
// Response 200
{ "status": "success", "message": "Pipeline triggered successfully via HTTP API" }

// Also supports (only reachable when ENABLE_PIPELINE_DOCKER_FALLBACK=true, see below):
// { "status": "success", "message": "Pipeline triggered successfully via docker restart" }
// { "status": "success", "message": "Pipeline triggered successfully via docker-compose restart" }

// Error 502 — HTTP trigger unreachable and the Docker CLI fallback is disabled
//              (the production default). Body is sanitized: a generic message plus
//              a request ID for correlating to server-side logs — no stderr, paths,
//              or container names are ever returned to the client.
{ "detail": "Pipeline trigger failed (request <request_id>)" }

// Error 502 — Docker CLI fallback is enabled but all trigger methods failed
//              (same sanitized shape as above: generic message plus request ID)
```
The HTTP trigger to the Auto_detect watcher (`PIPELINE_TRIGGER_URL` /
`http://localhost:9091/trigger` / `http://host.docker.internal:9091/trigger`)
is tried first and is the only path used in production. If it's unreachable,
a local Docker CLI fallback (shelling out to `docker restart` /
`docker-compose restart` from the API process — a privileged operation) only
runs when the server has `ENABLE_PIPELINE_DOCKER_FALLBACK` set to exactly
`"true"` (case-insensitive, whitespace-tolerant); it is unset/`false` by
default, so production deployments never shell out from the API process.

### GET /api/pipeline-status
```json
// Response 200 — proxied from auto-detect watcher (http://localhost:9091/status)
{ "busy": false, "cycle_count": 42 }

// Error 503 — all upstream URLs failed
```

---

## History

### GET /api/history
```json
// Response 200 — the caller's own records; an admin caller gets all records
[
  {
    "id": 1,
    "pr_no": "PR2024001",
    "order_lot": "MTDQS0906.1",
    "revision": "A",
    "timepoint": "T0",
    "user_id": "EMP001",
    "file_name": "DPA_Report_PR2024001_T0_MTDQS0906.1_20240115_103045.pptx",
    "file_path": "D:\\DPA\\output\\...",
    "created_at": "2024-01-15T10:30:45"
  }
]
```

### GET /api/history/{record_id}/download
```
// Response 200 — FileResponse (PPTX)
Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation
Content-Disposition: attachment; filename="DPA_Report_..."

// Error 403 — caller is neither the record's owner nor an admin
// Error 404 — record not found or file missing on disk
```

### DELETE /api/history/{record_id}
```json
// Response 200
{ "status": "deleted" }

// Error 403 — caller is neither the record's owner nor an admin
// Error 404 — record not found
```

---

## File Serving

### GET /api/image?path={windows_path}
```
// path — Windows absolute path (DB-stored), translated via IMAGE_WIN_ROOT → IMAGE_MOUNT_ROOT
// Response 200 — FileResponse (image/jpeg or image/png)
// Error 403 — path outside IMAGE_MOUNT_ROOT
// Error 404 — file not found
```

### GET /api/download-report?path={path} **[rate: 10/min]**
```
// path — must be inside OUTPUT_DIR or IMAGE_MOUNT_ROOT
// Response 200 — FileResponse (PPTX)
// Error 403 — path outside allowed roots
// Error 404 — file not found
```

### GET /api/bond-excel-path?pr_no={pr_no}&timepoint={tp}&lot={lot}
```json
// Response 200
{ "path": "D:\\Auto_detect\\Result\\...\\BOND_ABILITY_REPORT.xlsx" }
// path is null if not found
```

---

## Dashboard

### GET /api/stats
```json
// Response 200
{ "total": 42, "generated": 42, "failed": 0 }
```

---

## Health Check **[public]**

### GET /health
```json
// Response 200 — no auth, no DB call
{ "status": "ok" }

// Response 200 — caller presents a valid JWT (cookie or Authorization: Bearer)
// with role == "admin" (decoded from the token only, no DB round-trip)
{ "status": "ok", "gitSha": "abc1234" }
```
`gitSha` echoes the `APP_GIT_SHA` env var baked into the image at build time
(see `docker-compose.yml`'s `APP_GIT_SHA: ${GIT_SHA:-unknown}` build arg);
it's `"unknown"` if the image was built without `GIT_SHA` exported. A
missing/invalid/expired token is never an error here — it just omits
`gitSha` — so the endpoint stays safe to hit from load balancers and uptime
probes with no auth at all.

---

## Account Administration — `/api/admin`

All routes below require `role == "admin"` via `Depends(require_role("admin"))`.
The frontend also hides the Account Management nav item for non-admins, but
that's a convenience only — every route enforces the role check server-side
regardless of what the UI shows.

Every lifecycle action (`approve`/`disable`/`restore`/`reset-link`/delete)
writes an audit row to `account_audit_logs` (before/after JSONB snapshots,
actor/target, timestamp) and mirrors a sanitized copy to a JSONL file at
`{AUDIT_LOG_ROOT}/{YYYY-MM-DD}.jsonl` (see Configuration below). The JSONL
mirror is **fail-open**: if the write fails (permission, disk full,
unreachable path) it's logged as a warning and swallowed — it never blocks
or undoes the already-committed DB action/response. No password, password
hash, reset token, request body, header, or query string is ever written to
either the audit table or the JSONL mirror; `audit_service._sanitize_state`
strips any key whose name contains `password`, `hash`, `token`, `secret`,
`authorization`, or `cookie` as a last line of defense even if a caller
accidentally includes one.

### GET /api/admin/accounts
```
// Query: status, search, cursor, limit (default 50, max 100)
// Response 200
{
  "items": [
    { "user_id": "EMP001", "full_name": "John Doe", "email": "john@example.com",
      "role": "QA Engineer", "account_status": "active", "is_active": true,
      "session_version": 1, "created_at": "2026-08-27T10:00:00+00:00" }
  ],
  "next_cursor": "EMP001"   // pass back as ?cursor= for the next page, or null on the last page
}
```

### POST /api/admin/accounts/{user_id}/approve
### POST /api/admin/accounts/{user_id}/restore
```json
// Response 200
{ "user_id": "EMP002", "account_status": "active", "is_active": true }

// Error 404 — user not found
```

### POST /api/admin/accounts/{user_id}/disable
```json
// Response 200
{ "user_id": "EMP002", "account_status": "disabled", "is_active": false }

// Error 404 — user not found
// Error 409 — target is the caller's own account, or the last active admin
```

### POST /api/admin/accounts/{user_id}/reset-link
```json
// Response 200 — resetUrl is returned exactly once and never stored raw;
// only its SHA-256 hash is persisted (password_reset_tokens.token_hash).
// The link expires 30 minutes after creation and is usable exactly once.
{ "resetUrl": "http://localhost:9090/reset-password/<one-time-token>" }

// Error 404 — user not found
```

### DELETE /api/admin/accounts/{user_id}
```json
// Request — both fields required; confirmUserId must exactly match {user_id}
{ "confirmUserId": "EMP002", "reason": "Duplicate account, confirmed with employee" }

// Response 200
{ "user_id": "EMP002", "deleted": true }

// Error 400 — reason blank, or confirmUserId does not match the target
// Error 404 — user not found
// Error 409 — target is the caller's own account, or the last active admin
// Error 422 — request body missing confirmUserId/reason
```
Permanent delete is irreversible: the row is removed from `users`, but an
audit row (before-state snapshot minus `password_hash`, plus the typed
`reason`) is written first, on the same connection/transaction as the
`DELETE`, so the audit trail can never claim a deletion that didn't actually
happen (or vice versa).

### GET /api/admin/accounts/{user_id}/activity
```
// Query: limit (default 50, max 100), cursor (an occurred_at ISO timestamp
// from a previous page's next_cursor)
// Response 200 — paged account_audit_logs rows for this account, newest first
{
  "items": [
    { "id": 1, "actor_user_id": "ADMIN1", "target_user_id": "EMP002",
      "action": "disable", "before_state": {"account_status": "active"},
      "after_state": {"account_status": "disabled"},
      "occurred_at": "2026-08-27T10:05:00+00:00" }
  ],
  "next_cursor": "2026-08-27T10:05:00+00:00"
}
```

### GET /api/admin/accounts/{user_id}/performance
```
// Query: start, end (ISO datetimes; half-open range — start inclusive, end
// exclusive — so results stay aligned with the (user_id, occurred_at DESC)
// index on request_telemetry; both optional, an omitted bound is unbounded)
// Response 200 — aggregate, never raw per-request rows
{
  "request_count": 240,
  "error_count": 3,
  "avg_duration_ms": 84.2,
  "max_duration_ms": 512.0
}
```

### GET /api/admin/sessions
```
// Query: user_id (optional filter), limit (default 50, max 100),
// cursor (a started_at ISO timestamp from a previous page's next_cursor)
// Response 200 — paged user_sessions rows across all accounts, newest first
{
  "items": [
    { "id": 1, "user_id": "EMP001", "ip_address": "10.153.90.42",
      "user_agent": "Mozilla/5.0 ...", "session_id": "6c2b...-uuid",
      "started_at": "2026-08-27T09:00:00+00:00",
      "last_seen_at": "2026-08-27T09:40:00+00:00",
      "logged_out_at": null, "expires_at": "2026-08-28T09:00:00+00:00",
      "revoked_at": null }
  ],
  "next_cursor": "2026-08-27T09:00:00+00:00"
}
```

### GET /api/admin/performance/daily
```
// Query: days (default 30, max 365), route (optional exact-match filter)
// Response 200 — endpoint_latency_daily rollup rows, newest day first.
// Populated once a day by an in-process background task owned by the app's
// lifespan (see backend/main.py's _daily_rollup_loop, TELEMETRY_ROLLUP_HOUR_UTC)
// -- not by every request. An empty result for today means that day's slot
// hasn't run yet, not that there was no traffic.
{
  "items": [
    { "route": "/api/product-requests", "day": "2026-08-27",
      "request_count": 240, "error_count": 3,
      "avg_latency_ms": 84.2, "p95_latency_ms": 210.0, "max_latency_ms": 512.0 }
  ]
}
```

### GET /api/admin/performance/daily/detail
```
// Query: route (required, exact match), day (required, YYYY-MM-DD, UTC
// calendar day), limit (default 50, max 100),
// cursor (an occurred_at ISO timestamp from a previous page's next_cursor)
// Response 200 — raw request_telemetry rows for that route+day, newest
// first: drill-down for one row of GET /performance/daily, showing which
// user made each request behind its aggregate counts.
{
  "items": [
    { "id": 1, "user_id": "EMP001", "method": "GET", "status_code": 200,
      "duration_ms": 42.0, "occurred_at": "2026-08-27T09:00:00+00:00" }
  ],
  "next_cursor": null
}
```

### Retention

| Table | Window | Column |
| --- | --- | --- |
| `request_telemetry` | 90 days | `occurred_at` |
| `account_audit_logs` | 1 year | `occurred_at` |
| `user_sessions` | 1 year | `started_at` |
| `endpoint_latency_daily` | 1 year | `created_at` |
| `password_reset_tokens` | 7 days after expiry/use | `used_at` / `expires_at` |

Run the purge manually or on a schedule (e.g. a daily cron/Task Scheduler
job) from `backend/`:
```powershell
python scripts/purge_account_observability.py
```
Deletes use half-open, index-aligned predicates (`col < now() - interval
'...'`, never `DATE(col) < ...`) so they hit the existing indexes instead of
forcing a full table scan. Only per-table row counts are logged — never row
contents.

---

## Error Format

FastAPI default:
```json
{ "detail": "Error message here" }
```

Rate limit exceeded (429):
```json
{ "error": "Rate limit exceeded: 5 per 1 minute" }
```
