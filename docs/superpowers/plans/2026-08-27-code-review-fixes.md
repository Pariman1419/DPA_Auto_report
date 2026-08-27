# Code Review Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 7 findings from the two-axis `/code-review` run (spec: `docs/superpowers/specs/2026-08-27-code-review-fixes-design.md`) — a real count bug, four Standards hard violations, three Standards smells, and one undocumented feature — plus one adjacent bug found during Task 1's self-review (same root cause, different function, added by explicit user confirmation), without touching anything else in the codebase.

**Architecture:** Nine sequential tasks (Task 0 prerequisite + Tasks 1-8) against the existing FastAPI backend (`backend/`). No new modules, no new abstractions — every task is a targeted edit to an existing file plus its test. Tests use the existing `pytest` suite under `tests/` (fixtures in `tests/conftest.py`: `client`, `mock_db`, `auth_cookies` = QA Engineer `EMP001`, `admin_cookies` = admin).

**Tech Stack:** Python 3, FastAPI, psycopg2, slowapi (rate limiting), pytest + `starlette.testclient.TestClient`.

## Global Constraints

- Every backend module must log via `from logger import get_logger` — never `print()` (per `CLAUDE.md`).
- Every new/modified sensitive endpoint gets `@limiter.limit(...)` per `CLAUDE.md`, EXCEPT `/api/image` (see Task 6 rationale — do not add a rate limit there).
- File-serving endpoints must resolve the path and assert it's within an allowed root before serving (already true for `/download-report` and `/image` — do not weaken this).
- `require_role(*roles)` in `backend/routers/auth.py` is the standard way to gate by role.
- Run the full backend test suite (`cd backend && python -m pytest ../tests -v`) after every task and confirm no regressions before moving to the next task.
- All 7 findings from the spec must be addressed; nothing outside them.

---

## Task 0: Disable the product_request rate limiter in tests (prerequisite)

**Why first:** Tasks 5 and 6 add `@limiter.limit(...)` to endpoints that already have passing tests (`/generate-report`, `/download-report`, `/register`, `/approve/{token}`). The `limiter` instance in `backend/routers/product_request.py` is a **separate object** from `app.state.limiter` (the one `main.py` creates) — slowapi's `@limiter.limit()` decorator checks `self.enabled` on the instance it was created from, not on `app.state.limiter`. The test suite's `app` fixture (`tests/conftest.py:48-51`) currently only disables `app.state.limiter` and `routers.auth.limiter`; it never disables `routers.product_request.limiter`. Without this task, `/trigger-pipeline`'s existing `@limiter.limit("3/minute")` already silently isn't tested, and the new limits added in Task 5/6 would cause flaky 429s across the test session (repeated test runs hitting the same endpoint from the same TestClient "IP" within the same 60s window).

**Files:**
- Modify: `tests/conftest.py:45-52`

**Interfaces:**
- Consumes: `routers.product_request.limiter` (a `slowapi.Limiter` instance) — created in Task 5/6's target file, already exists today at `backend/routers/product_request.py:23`.
- Produces: nothing new — this only changes test setup.

- [ ] **Step 1: Add the missing limiter-disable line to the `app` fixture**

In `tests/conftest.py`, change:

```python
@pytest.fixture(scope="session")
def app():
    from main import app as _app
    if hasattr(_app, "state") and hasattr(_app.state, "limiter"):
        _app.state.limiter.enabled = False
    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = False
    return _app
```

to:

```python
@pytest.fixture(scope="session")
def app():
    from main import app as _app
    if hasattr(_app, "state") and hasattr(_app.state, "limiter"):
        _app.state.limiter.enabled = False
    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = False
    from routers.product_request import limiter as pr_limiter
    pr_limiter.enabled = False
    return _app
```

- [ ] **Step 2: Run the full suite to confirm nothing broke**

Run: `cd backend && python -m pytest ../tests -v`
Expected: same pass count as before this change (this step only disables a limiter that wasn't being exercised yet — no test should change behavior).

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: disable product_request rate limiter in test app fixture"
```

---

## Task 1: Fix the CR / Cross-Section Inspection count bug

**Files:**
- Modify: `backend/services/product_request_service.py:404-406` (SQL `FILTER` clause), `:420-422` (`next()` lookup)
- Test: `tests/unit/test_cr_cross_section_count.py` (new)

**Interfaces:**
- Consumes: `services.product_request_service.list_timepoint_folders(pr_number: str, timepoint: str, lot: str) -> list[dict]` (existing, unchanged signature) and the `mock_db` fixture from `tests/conftest.py` (patches `DBConnector.get_dpa_connection`/`release_dpa_connection`, returns `(conn, cursor)` where `cursor.fetchall`/`cursor.fetchone` are configurable `MagicMock`s).
- Produces: no new public interface — same function, corrected internal logic.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_cr_cross_section_count.py`:

```python
"""
Regression test for the CR / Cross-Section Inspection count bug.

Bug: "CR" is a substring of "CROSS", so a loose LIKE '%CR%' / "CR" in x
match can pick up a "CROSS SECTION INSPECTION" row when computing the
C-R (destructive cross-section) valid file count. The display-assignment
loop already excludes "CROSS" (product_request_service.py ~line 455);
this test targets the earlier point in the same function where the
substring bug can still leak through, independent of row order.
"""
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.unit


def test_cross_section_row_does_not_pollute_cr_count(mock_db):
    """
    Seed a CROSS SECTION INSPECTION row ahead of the real 6.C-R row
    (reversed from alphabetical order) and assert the C-R file count
    comes from the true C-R row, not the CROSS row.
    """
    from services.product_request_service import list_timepoint_folders

    conn, cur = mock_db
    # (category, file_count, imc_valid_count, cr_valid_count)
    # CROSS row deliberately listed FIRST so a buggy `next()` without a
    # "CROSS" exclusion would pick its cr_valid_count (99) instead of
    # the real 6.C-R row's (4).
    cur.fetchall.return_value = [
        ("CROSS SECTION INSPECTION", 12, 0, 99),
        ("6.C-R", 4, 0, 4),
    ]
    cur.fetchone.return_value = (0, 0, 3)  # imc_count, bond_count, sem_count

    with patch(
        "services.product_request_service.find_bond_ability_excel",
        return_value=None,
    ):
        folders = list_timepoint_folders("PR2024001", "T0", "MTDQS0906.1")

    cr_folder = next(f for f in folders if f["name"] == "6.C-R")
    assert cr_folder["fileCount"] == 4

    cross_folder = next(
        f for f in folders if f["name"] == "CROSS SECTION INSPECTION"
    )
    assert cross_folder["fileCount"] == 12  # its own file_count, untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest ../tests/unit/test_cr_cross_section_count.py -v`
Expected: FAIL — `cr_folder["fileCount"] == 4` fails because `cr_valid_file_count` currently resolves to `99` (the CROSS row's count), since neither the `next()` lookup nor the SQL filter excludes `"CROSS"`.

- [ ] **Step 3: Fix the SQL filter**

In `backend/services/product_request_service.py`, change (around line 403-406):

```python
                    COUNT(*) FILTER (
                        WHERE (UPPER(category) LIKE '%%C-R%%' OR UPPER(category) LIKE '%%CR%%')
                          AND image_seq IN ({cr_placeholders})
                    ) AS cr_valid_count
```

to:

```python
                    COUNT(*) FILTER (
                        WHERE (UPPER(category) LIKE '%%C-R%%' OR UPPER(category) LIKE '%%CR%%')
                          AND UPPER(category) NOT LIKE '%%CROSS%%'
                          AND image_seq IN ({cr_placeholders})
                    ) AS cr_valid_count
```

- [ ] **Step 4: Fix the `next()` lookup**

In the same file, change (around line 420-422):

```python
            cr_valid_file_count  = next(
                (r[3] for r in raw_rows if "C-R" in r[0].upper() or "CR" in r[0].upper()), 0
            )
```

to:

```python
            cr_valid_file_count  = next(
                (r[3] for r in raw_rows
                 if ("C-R" in r[0].upper() or "CR" in r[0].upper())
                 and "CROSS" not in r[0].upper()),
                0,
            )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python -m pytest ../tests/unit/test_cr_cross_section_count.py -v`
Expected: PASS

- [ ] **Step 6: Run the full suite to confirm no regressions**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass (no test previously depended on the buggy behavior).

- [ ] **Step 7: Commit**

```bash
git add backend/services/product_request_service.py tests/unit/test_cr_cross_section_count.py
git commit -m "fix: exclude CROSS SECTION INSPECTION rows from C-R valid count"
```

---

## Task 2: Replace `print()` with the logger in `auth_service.py` and `db_connector.py`

**Files:**
- Modify: `backend/services/auth_service.py:1-11`
- Modify: `backend/services/db_connector.py:15-20`

**Interfaces:**
- Consumes: `logger.get_logger(name: str) -> logging.Logger` (existing, `backend/logger.py:51`).
- Produces: nothing new — same fail-fast behavior (`sys.exit(1)`), different reporting call.

- [ ] **Step 1: Edit `auth_service.py`**

Change:

```python
import os
import sys
from datetime import datetime, timezone, timedelta

import bcrypt
from jose import jwt

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    print("[ERROR] JWT_SECRET_KEY is not set. Set it in .env before starting.", file=sys.stderr)
    sys.exit(1)
```

to:

```python
import os
import sys
from datetime import datetime, timezone, timedelta

import bcrypt
from jose import jwt

from logger import get_logger

log = get_logger("auth_service")

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    log.error("JWT_SECRET_KEY is not set. Set it in .env before starting.")
    sys.exit(1)
```

- [ ] **Step 2: Edit `db_connector.py`**

Change (line 18):

```python
def _require(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        print(f"[ERROR] Required environment variable '{name}' is not set.", file=sys.stderr)
        sys.exit(1)
    return val
```

to:

```python
def _require(name: str) -> str:
    val = os.getenv(name, "")
    if not val:
        log.error("Required environment variable '%s' is not set.", name)
        sys.exit(1)
    return val
```

(`log` is already defined at `db_connector.py:9` — no new import needed.)

- [ ] **Step 3: Run the full suite to confirm the import chain still works**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass — `tests/conftest.py` sets all required env vars before import, so `_require()`/`SECRET_KEY` checks never trigger `sys.exit(1)` during tests; this only verifies the module still imports cleanly.

- [ ] **Step 4: Commit**

```bash
git add backend/services/auth_service.py backend/services/db_connector.py
git commit -m "fix: use logger instead of print() in auth_service and db_connector"
```

---

## Task 3: Deduplicate path translation — delete `_resolve_image_path`

**Files:**
- Modify: `backend/routers/product_request.py:12-17` (imports), `:76-93` (`download_report`), `:180-199` (delete `_resolve_image_path`), `:202-217` (`get_image`)
- Test: `tests/api/test_product_request.py` (existing tests must still pass unmodified — this is a pure refactor)

**Interfaces:**
- Consumes: `services.product_request_service._translate_image_path(path: str | None) -> str | None` (existing, `backend/services/product_request_service.py:27`).
- Produces: `download_report` and `get_image` now resolve paths via the shared function; `_resolve_image_path` no longer exists.

- [ ] **Step 1: Run the existing file-serving tests to record the current passing baseline**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py -v -k "download_report or get_image"`
Expected: PASS (4 tests: `test_download_report_success`, `test_download_report_path_traversal_denied`, `test_get_image_success`, `test_get_image_path_traversal_denied`).

- [ ] **Step 2: Add the import**

In `backend/routers/product_request.py`, change the import block (lines 12-17):

```python
from services.product_request_service import (
    read_product_request, list_product_requests, list_timepoints,
    list_timepoint_folders, get_generation_stats, list_lots, list_lots_registry,
    list_generation_history, get_history_record, delete_history_record,
    get_next_revision, save_generation_history, list_preview_images, list_preview_imc, list_preview_bond, list_preview_sem
)
```

to:

```python
from services.product_request_service import (
    read_product_request, list_product_requests, list_timepoints,
    list_timepoint_folders, get_generation_stats, list_lots, list_lots_registry,
    list_generation_history, get_history_record, delete_history_record,
    get_next_revision, save_generation_history, list_preview_images, list_preview_imc, list_preview_bond, list_preview_sem,
    _translate_image_path,
)
```

- [ ] **Step 3: Delete `_resolve_image_path` and update its two call sites**

Delete the whole function (lines 180-199):

```python
def _resolve_image_path(path: str) -> pathlib.Path:
    """
    Translate the path from DB (which may be a Windows absolute path) to the
    actual filesystem path in this environment.

    IMAGE_WIN_ROOT  — prefix stored in DB  (default: D:\\Auto_detect\\Result)
    IMAGE_MOUNT_ROOT — where that folder is mounted here (default: same as WIN_ROOT)
    """
    win_root   = os.getenv("IMAGE_WIN_ROOT",   r"D:\Auto_detect\Result")
    mount_root = os.getenv("IMAGE_MOUNT_ROOT", win_root)

    # Normalise separators for comparison (handle both \ and /)
    norm_path = path.replace("\\", "/")
    norm_win  = win_root.replace("\\", "/")

    if norm_path.lower().startswith(norm_win.lower()):
        relative = norm_path[len(norm_win):].lstrip("/")
        path = str(pathlib.PurePosixPath(mount_root) / relative)

    return pathlib.Path(path)
```

In `download_report` (line 83), change:

```python
    requested = _resolve_image_path(path).resolve()
```

to:

```python
    requested = pathlib.Path(_translate_image_path(path)).resolve()
```

In `get_image` (line 208), change:

```python
    requested   = _resolve_image_path(path).resolve()
```

to:

```python
    requested   = pathlib.Path(_translate_image_path(path)).resolve()
```

- [ ] **Step 4: Run the same tests to verify no regression**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py -v -k "download_report or get_image"`
Expected: PASS — identical to the Step 1 baseline. `_translate_image_path` and the deleted `_resolve_image_path` performed the same normalization; only the wrapper type (`str` → `pathlib.Path`) changed, which both old call sites already did via `.resolve()`.

- [ ] **Step 5: Run the full suite**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/product_request.py
git commit -m "refactor: dedupe image path translation, use shared _translate_image_path"
```

---

## Task 4: Consolidate the duplicated inline logger in `product_request.py`

**Files:**
- Modify: `backend/routers/product_request.py:1-23` (imports), `:130-135` (`generate_dpa_report`), `:240-252` (`trigger_pipeline`)

**Interfaces:**
- Consumes: `logger.get_logger(name: str) -> logging.Logger`.
- Produces: module-level `log` in `product_request.py`, replacing the 3 inline `from logger import get_logger as _gl` call sites.

- [ ] **Step 1: Add the module-level logger**

In `backend/routers/product_request.py`, change the top of the file:

```python
import os
import pathlib
import subprocess
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.product_request_service import (
    read_product_request, list_product_requests, list_timepoints,
    list_timepoint_folders, get_generation_stats, list_lots, list_lots_registry,
    list_generation_history, get_history_record, delete_history_record,
    get_next_revision, save_generation_history, list_preview_images, list_preview_imc, list_preview_bond, list_preview_sem,
    _translate_image_path,
)
from models.schemas import ProductRequestData, ProductRequestListItem, GenerateReportRequest
from services.report_generator import DPAReportGenerator, OUTPUT_DIR
from routers.auth import get_current_user

router = APIRouter(prefix="/api", tags=["Product Request"])
limiter = Limiter(key_func=get_remote_address)
```

to:

```python
import os
import pathlib
import subprocess
import urllib.request
import urllib.error

from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.product_request_service import (
    read_product_request, list_product_requests, list_timepoints,
    list_timepoint_folders, get_generation_stats, list_lots, list_lots_registry,
    list_generation_history, get_history_record, delete_history_record,
    get_next_revision, save_generation_history, list_preview_images, list_preview_imc, list_preview_bond, list_preview_sem,
    _translate_image_path,
)
from models.schemas import ProductRequestData, ProductRequestListItem, GenerateReportRequest
from services.report_generator import DPAReportGenerator, OUTPUT_DIR
from routers.auth import get_current_user
from logger import get_logger

router = APIRouter(prefix="/api", tags=["Product Request"])
limiter = Limiter(key_func=get_remote_address)
log = get_logger("product_request")
```

- [ ] **Step 2: Replace the inline logger in `generate_dpa_report`**

Change (around line 130-135):

```python
        from logger import get_logger as _gl
        _log = _gl("product_request")
        _log.info("Report generated — PR=%s Lot=%s TP=%s metadata=%s images=%d missing=%d file=%s",
                  req.prNumber, req.lot, req.timepoint,
                  stats['metadata_found'], stats['images_found'], stats['images_missing'],
                  os.path.basename(output_path))
```

to:

```python
        log.info("Report generated — PR=%s Lot=%s TP=%s metadata=%s images=%d missing=%d file=%s",
                  req.prNumber, req.lot, req.timepoint,
                  stats['metadata_found'], stats['images_found'], stats['images_missing'],
                  os.path.basename(output_path))
```

- [ ] **Step 3: Replace the inline logger in `trigger_pipeline`**

Change (around line 236-252):

```python
    triggered_via_http = False
    http_error_msg = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, data=b'')
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    triggered_via_http = True
                    from logger import get_logger as _gl
                    _gl("product_request").info(f"Pipeline successfully triggered via HTTP URL: {url}")
                    break
        except Exception as e:
            http_error_msg = str(e)

    if triggered_via_http:
        return {"status": "success", "message": "Pipeline triggered successfully via HTTP API"}

    # 2. Try via docker CLI commands as fallbacks
    from logger import get_logger as _gl
    _log = _gl("product_request")
    _log.warning(f"Failed to trigger pipeline via HTTP URLs (last error: {http_error_msg}). Trying local Docker CLI fallback...")

    try:
        # Try docker restart first
        res = subprocess.run(["docker", "restart", "auto_detect-pipeline-1"], capture_output=True, text=True, timeout=10.0)
        if res.returncode == 0:
            _log.info("Pipeline container auto_detect-pipeline-1 restarted successfully")
            return {"status": "success", "message": "Pipeline triggered successfully via docker restart"}
        else:
            # Try docker-compose restart as second fallback
            res2 = subprocess.run(["docker-compose", "-f", r"D:\Auto_detect\docker-compose.yml", "restart", "pipeline"], capture_output=True, text=True, timeout=15.0)
            if res2.returncode == 0:
                _log.info("Pipeline restarted successfully via docker-compose restart")
                return {"status": "success", "message": "Pipeline triggered successfully via docker-compose restart"}
            else:
                raise Exception(f"docker restart failed: {res.stderr}; docker-compose restart failed: {res2.stderr}")
    except Exception as e:
        _log.error(f"Failed to trigger pipeline via Docker CLI fallback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger pipeline. Error: {str(e)}"
        )
```

to:

```python
    triggered_via_http = False
    http_error_msg = ""
    for url in urls:
        try:
            req = urllib.request.Request(url, data=b'')
            with urllib.request.urlopen(req, timeout=3.0) as response:
                if response.status == 200:
                    triggered_via_http = True
                    log.info(f"Pipeline successfully triggered via HTTP URL: {url}")
                    break
        except Exception as e:
            http_error_msg = str(e)

    if triggered_via_http:
        return {"status": "success", "message": "Pipeline triggered successfully via HTTP API"}

    # 2. Try via docker CLI commands as fallbacks
    log.warning(f"Failed to trigger pipeline via HTTP URLs (last error: {http_error_msg}). Trying local Docker CLI fallback...")

    try:
        # Try docker restart first
        res = subprocess.run(["docker", "restart", "auto_detect-pipeline-1"], capture_output=True, text=True, timeout=10.0)
        if res.returncode == 0:
            log.info("Pipeline container auto_detect-pipeline-1 restarted successfully")
            return {"status": "success", "message": "Pipeline triggered successfully via docker restart"}
        else:
            # Try docker-compose restart as second fallback
            res2 = subprocess.run(["docker-compose", "-f", PIPELINE_COMPOSE_PATH, "restart", "pipeline"], capture_output=True, text=True, timeout=15.0)
            if res2.returncode == 0:
                log.info("Pipeline restarted successfully via docker-compose restart")
                return {"status": "success", "message": "Pipeline triggered successfully via docker-compose restart"}
            else:
                raise Exception(f"docker restart failed: {res.stderr}; docker-compose restart failed: {res2.stderr}")
    except Exception as e:
        log.error(f"Failed to trigger pipeline via Docker CLI fallback: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to trigger pipeline. Error: {str(e)}"
        )
```

Note: `PIPELINE_COMPOSE_PATH` is introduced in Task 6 (Step 1) — this task references it but Task 6 defines it. If executing tasks strictly in order, Task 6 runs after this one, so add a temporary literal here and let Task 6's edit replace it — OR (preferred, avoids a broken intermediate commit) do Task 6's Step 1 (env var definition) first as part of this task's Step 3, and let Task 6 skip re-adding it. **Resolution: move `PIPELINE_COMPOSE_PATH` definition into this task** — see Step 4 below.

- [ ] **Step 4: Define `PIPELINE_COMPOSE_PATH` now (pulled forward from Task 6 to avoid a broken intermediate state)**

In `backend/routers/product_request.py`, add this line right after `log = get_logger("product_request")` (from Step 1):

```python
PIPELINE_COMPOSE_PATH = os.getenv("PIPELINE_COMPOSE_PATH", r"D:\Auto_detect\docker-compose.yml")
```

So the top of the file now reads:

```python
router = APIRouter(prefix="/api", tags=["Product Request"])
limiter = Limiter(key_func=get_remote_address)
log = get_logger("product_request")
PIPELINE_COMPOSE_PATH = os.getenv("PIPELINE_COMPOSE_PATH", r"D:\Auto_detect\docker-compose.yml")
```

- [ ] **Step 5: Run the full suite**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass — no test patches `logger.get_logger` directly, so switching to a module-level logger doesn't affect assertions.

- [ ] **Step 6: Commit**

```bash
git add backend/routers/product_request.py
git commit -m "refactor: use module-level logger in product_request router, extract PIPELINE_COMPOSE_PATH"
```

---

## Task 5: Role / ownership gating

**Files:**
- Modify: `backend/routers/product_request.py:51-56` (`delete_history`), `:220-222` (`trigger_pipeline`)
- Test: `tests/api/test_product_request.py`

**Interfaces:**
- Consumes: `routers.auth.get_current_user`, `routers.auth.require_role(*roles: str)` (existing, `backend/routers/auth.py:43`, `:59`), `services.product_request_service.get_history_record(record_id: int) -> dict | None` (existing, `backend/services/product_request_service.py:705`, returns a dict including `"user_id"`).
- Produces: `DELETE /api/history/{record_id}` now 403s for a non-owner non-admin caller; `POST /api/trigger-pipeline` now requires `role == "admin"`.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_product_request.py`, replace the existing `test_delete_history_success` and `test_delete_history_not_found` (they currently don't mock `get_history_record`, which the new implementation will call first) and add ownership-check tests. Change:

```python
def test_delete_history_success(client, auth_cookies):
    """Delete endpoint returns status: deleted when deletion succeeds."""
    with patch("routers.product_request.delete_history_record", return_value=True):
        response = client.delete("/api/history/1", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}


def test_delete_history_not_found(client, auth_cookies):
    """Delete endpoint returns 404 if history record does not exist."""
    with patch("routers.product_request.delete_history_record", return_value=False):
        response = client.delete("/api/history/999", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"
```

to:

```python
def test_delete_history_success_owner(client, auth_cookies, sample_history):
    """Delete endpoint returns status: deleted when the caller owns the record.

    auth_cookies is a QA Engineer token for user_id "EMP001"; sample_history's
    user_id is also "EMP001" (see tests/conftest.py SAMPLE_HISTORY_ROW).
    """
    with patch("routers.product_request.get_history_record", return_value=dict(sample_history)), \
         patch("routers.product_request.delete_history_record", return_value=True):
        response = client.delete("/api/history/1", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}


def test_delete_history_success_admin_on_others_record(client, admin_cookies, sample_history):
    """Delete endpoint returns status: deleted when the caller is admin, even if not the owner."""
    other_users_record = dict(sample_history)
    other_users_record["user_id"] = "EMP999"
    with patch("routers.product_request.get_history_record", return_value=other_users_record), \
         patch("routers.product_request.delete_history_record", return_value=True):
        response = client.delete("/api/history/1", cookies=admin_cookies)
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}


def test_delete_history_forbidden_non_owner_non_admin(client, auth_cookies, sample_history):
    """Delete endpoint returns 403 if the caller is neither admin nor the record's owner."""
    other_users_record = dict(sample_history)
    other_users_record["user_id"] = "EMP999"
    with patch("routers.product_request.get_history_record", return_value=other_users_record):
        response = client.delete("/api/history/1", cookies=auth_cookies)
        assert response.status_code == 403
        assert response.json()["detail"] == "Insufficient permissions"


def test_delete_history_not_found(client, auth_cookies):
    """Delete endpoint returns 404 if history record does not exist."""
    with patch("routers.product_request.get_history_record", return_value=None):
        response = client.delete("/api/history/999", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"
```

Also add, in the same file (anywhere after the delete-history tests):

```python
def test_trigger_pipeline_forbidden_for_non_admin(client, auth_cookies):
    """trigger-pipeline is admin-only; a QA Engineer token gets 403."""
    response = client.post("/api/trigger-pipeline", cookies=auth_cookies)
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"


def test_trigger_pipeline_allowed_for_admin(client, admin_cookies):
    """trigger-pipeline succeeds for an admin token (HTTP path mocked)."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_response
        response = client.post("/api/trigger-pipeline", cookies=admin_cookies)
        assert response.status_code == 200
        assert response.json()["status"] == "success"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py -v -k "delete_history or trigger_pipeline"`
Expected: FAIL —
- `test_delete_history_success_owner` / `test_delete_history_success_admin_on_others_record` fail because `delete_history` doesn't call `get_history_record` yet (the patch target is never invoked, but that alone isn't the failure — the real failure comes after Step 3's edit if these are run again; for now, before any code change, `test_delete_history_forbidden_non_owner_non_admin` fails because the endpoint currently always allows the delete (no 403 raised) — this is the core regression check).
- `test_trigger_pipeline_forbidden_for_non_admin` fails because `trigger_pipeline` currently accepts any authenticated user (200/500, not 403).

- [ ] **Step 3: Implement the ownership check in `delete_history`**

In `backend/routers/product_request.py`, change (lines 51-56):

```python
@router.delete("/history/{record_id}")
def delete_history(record_id: int, _user=Depends(get_current_user)):
    ok = delete_history_record(record_id, delete_file=True)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")
    return {"status": "deleted"}
```

to:

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

- [ ] **Step 4: Implement admin-only gating on `trigger_pipeline`**

In `backend/routers/product_request.py`, add `require_role` to the import from `routers.auth` (change line ~20):

```python
from routers.auth import get_current_user
```

to:

```python
from routers.auth import get_current_user, require_role
```

Then change the `trigger_pipeline` signature (line 220-222):

```python
@router.post("/trigger-pipeline")
@limiter.limit("3/minute")
def trigger_pipeline(request: Request, _user=Depends(get_current_user)):
```

to:

```python
@router.post("/trigger-pipeline")
@limiter.limit("3/minute")
def trigger_pipeline(request: Request, _user=Depends(require_role("admin"))):
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py -v -k "delete_history or trigger_pipeline"`
Expected: PASS (6 tests: the 4 delete_history variants + 2 trigger_pipeline variants).

- [ ] **Step 6: Run the full suite**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/routers/product_request.py tests/api/test_product_request.py
git commit -m "feat: gate history delete by ownership/admin, pipeline trigger by admin role"
```

---

## Task 6: Rate limiting on remaining sensitive endpoints

**Files:**
- Modify: `backend/routers/product_request.py:76-93` (`download_report`), `:121-155` (`generate_dpa_report`)
- Modify: `backend/routers/auth.py:160-181` (`register`), `:184-211` (`approve_user`)
- Test: `tests/api/test_product_request.py`, `tests/api/test_auth.py`

**Interfaces:**
- Consumes: `slowapi.Limiter.limit(limit_value: str)` (existing decorator pattern, already used at `product_request.py:221` and `auth.py:72`).
- Produces: 429 responses beyond the stated limits on `/api/generate-report`, `/api/download-report`, `/api/auth/register`, `/api/auth/approve/{token}`. (`/api/image` is deliberately excluded — see spec §4 rationale: bulk gallery rendering would false-positive under any per-IP limit tight enough to matter.)

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_product_request.py`, add (near the existing `test_generate_report_success` / `test_download_report_success`):

```python
def test_generate_report_rate_limited(client, auth_cookies, tmp_path):
    """POST /api/generate-report is limited to 3/minute; the 4th call in a
    window returns 429."""
    gen_payload = {
        "prNumber": "PR2024001",
        "lot": "MTDQS0906.1",
        "timepoint": "T0",
        "userId": "EMP001",
        "selectedSections": {"EXTERNAL": True},
    }
    mock_out = str(tmp_path / "output_report.pptx")
    pathlib.Path(mock_out).touch()

    with patch("routers.product_request.get_next_revision", return_value="A"), \
         patch("routers.product_request.DPAReportGenerator") as mock_gen_cls, \
         patch("routers.product_request.save_generation_history"):
        mock_gen_inst = MagicMock()
        mock_gen_inst.generate.return_value = (mock_out, {"metadata_found": True, "images_found": 0, "images_missing": 0})
        mock_gen_cls.return_value = mock_gen_inst

        from routers.product_request import limiter as pr_limiter
        pr_limiter.enabled = True
        try:
            for _ in range(3):
                r = client.post("/api/generate-report", json=gen_payload, cookies=auth_cookies)
                assert r.status_code == 200
            r = client.post("/api/generate-report", json=gen_payload, cookies=auth_cookies)
            assert r.status_code == 429
        finally:
            pr_limiter.enabled = False


def test_download_report_rate_limited(client, auth_cookies):
    """GET /api/download-report is limited to 10/minute; the 11th call in a
    window returns 429."""
    dummy_report = pathlib.Path(OUTPUT_DIR) / "DPA_Report_ratelimit_test.pptx"
    dummy_report.write_bytes(b"report data")

    from routers.product_request import limiter as pr_limiter
    pr_limiter.enabled = True
    try:
        for _ in range(10):
            r = client.get(f"/api/download-report?path={dummy_report}", cookies=auth_cookies)
            assert r.status_code == 200
        r = client.get(f"/api/download-report?path={dummy_report}", cookies=auth_cookies)
        assert r.status_code == 429
    finally:
        pr_limiter.enabled = False
        if dummy_report.exists():
            dummy_report.unlink()
```

In `tests/api/test_auth.py`, add:

```python
def test_register_rate_limited(client, mock_db):
    """POST /api/auth/register is limited to 5/minute; the 6th call in a
    window returns 429."""
    client.cookies.clear()
    conn, cur = mock_db
    cur.fetchone.return_value = None

    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = True
    try:
        with patch("routers.auth.send_approval_email"):
            for i in range(5):
                payload = {
                    "userId": f"EMPRL{i}",
                    "fullName": "Rate Limit Test",
                    "email": "ratelimit@company.com",
                    "password": "password123",
                }
                r = client.post("/api/auth/register", json=payload)
                assert r.status_code == 200
            r = client.post("/api/auth/register", json=payload)
            assert r.status_code == 429
    finally:
        auth_limiter.enabled = False


def test_approve_user_rate_limited(client, mock_db, admin_cookies):
    """GET /api/auth/approve/{token} is limited to 5/minute; the 6th call
    in a window returns 429."""
    conn, cur = mock_db
    cur.fetchone.return_value = (True,)  # already-active short-circuits DB write path

    from routers.auth import limiter as auth_limiter
    auth_limiter.enabled = True
    try:
        with patch("routers.auth._ts.loads", return_value="EMP999"):
            for _ in range(5):
                r = client.get("/api/auth/approve/some_token", cookies=admin_cookies)
                assert r.status_code == 200
            r = client.get("/api/auth/approve/some_token", cookies=admin_cookies)
            assert r.status_code == 429
    finally:
        auth_limiter.enabled = False
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py ../tests/api/test_auth.py -v -k "rate_limited"`
Expected: FAIL — none of these 4 endpoints have `@limiter.limit(...)` yet, so every call in the loop returns its normal success status and the final assertion (`== 429`) fails.

- [ ] **Step 3: Add the decorator to `generate_dpa_report`**

In `backend/routers/product_request.py`, change (line 121-122):

```python
@router.post("/generate-report")
def generate_dpa_report(req: GenerateReportRequest, _user=Depends(get_current_user)):
```

to:

```python
@router.post("/generate-report")
@limiter.limit("3/minute")
def generate_dpa_report(request: Request, req: GenerateReportRequest, _user=Depends(get_current_user)):
```

- [ ] **Step 4: Add the decorator to `download_report`**

Change (line 76-77):

```python
@router.get("/download-report")
def download_report(path: str, _user=Depends(get_current_user)):
```

to:

```python
@router.get("/download-report")
@limiter.limit("10/minute")
def download_report(request: Request, path: str, _user=Depends(get_current_user)):
```

- [ ] **Step 5: Add the decorator to `register` and `approve_user` in `auth.py`**

In `backend/routers/auth.py`, change (line 160-161):

```python
@router.post("/register")
def register(req: RegisterRequest):
```

to:

```python
@router.post("/register")
@limiter.limit("5/minute")
def register(request: Request, req: RegisterRequest):
```

Change (line 184-185):

```python
@router.get("/approve/{token}")
def approve_user(token: str, _admin=Depends(require_admin)):
```

to:

```python
@router.get("/approve/{token}")
@limiter.limit("5/minute")
def approve_user(request: Request, token: str, _admin=Depends(require_admin)):
```

- [ ] **Step 6: Run the new tests to verify they pass**

Run: `cd backend && python -m pytest ../tests/api/test_product_request.py ../tests/api/test_auth.py -v -k "rate_limited"`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the full suite**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass — Task 0 already disabled `pr_limiter`/`auth_limiter` by default, and each new rate-limit test explicitly re-enables then restores its own limiter in a `finally` block, so it doesn't leak into other tests.

- [ ] **Step 8: Commit**

```bash
git add backend/routers/product_request.py backend/routers/auth.py tests/api/test_product_request.py tests/api/test_auth.py
git commit -m "feat: add rate limiting to generate-report, download-report, register, and approve endpoints"
```

---

## Task 7: Document the OpenTelemetry addition in the spec

**Files:**
- Modify: `business_domain_requirements.md`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing (documentation only) — no code changes in this task.

- [ ] **Step 1: Read the current file to find the insertion point**

Run: this step is a manual read, not a shell command — open `business_domain_requirements.md` and locate the end of the "ขั้นตอนการทำงานหลัก (Core Workflow)" section (section 3, currently ends before a section 4, if any — insert the new section immediately after section 3's closing content, before whatever section follows).

- [ ] **Step 2: Add the new section**

Insert a new section (numbered to fit the existing sequence — if section 3 is followed by section 4, this becomes a new section between them, renumber only if necessary to avoid a duplicate number) with this content:

```markdown
## Observability (Distributed Tracing)

ระบบ Backend มีการติดตั้ง OpenTelemetry สำหรับ distributed tracing โดย export ผ่าน OTLP ไปยัง collector ภายนอก (เช่น Jaeger)

- **ทำอะไร:** เก็บ trace ของทุก request ที่เข้ามาที่ FastAPI backend เพื่อดู latency และ error แต่ละ endpoint รวมถึง pipeline การ generate รายงาน
- **ทำไม:** เพิ่มความสามารถในการ debug และ monitor ประสิทธิภาพของระบบใน production ซึ่งไม่มี requirement เดิมครอบคลุมส่วนนี้ — เป็นการเพิ่มเติมที่ทีมยอมรับและบันทึกย้อนหลัง (เดิมถูกเพิ่มเข้ามาในโค้ดโดยไม่มีเอกสารรองรับ พบจาก code review วันที่ 2026-08-27)
- **Infra dependency ใหม่:** Backend คาดหวังว่า Docker network ชื่อ `observability-net` (external) จะมีอยู่แล้วในสภาพแวดล้อมที่ deploy (เช่น OTEL collector หรือ Jaeger stack) — เป็น precondition ก่อน deploy เดียวกับ `DB_HOST` ที่ต้องมี PostgreSQL พร้อมใช้งาน การเริ่มระบบจะไม่ fail หาก network นี้ไม่มี (wrapped in try/except ที่ `backend/main.py`), แต่ tracing จะไม่ทำงาน
```

- [ ] **Step 3: Verify the file still renders as valid Markdown**

Run: this is a documentation-only change — no automated test applies. Manually confirm the new section doesn't break the existing Markdown table/heading structure by re-reading the file top-to-bottom.

- [ ] **Step 4: Run the full backend suite one more time as a final sanity check**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass (this task touches no code).

- [ ] **Step 5: Commit**

```bash
git add business_domain_requirements.md
git commit -m "docs: document OpenTelemetry tracing addition and observability-net dependency"
```

---

## Task 8: Fix the same CR/CROSS substring bug in sort priority

**Discovered during Task 1's self-review, not part of the original 7 spec findings** — same root cause (`"CR"` is a substring of `"CROSS"`), different function. Added to this plan by explicit user confirmation.

**Files:**
- Modify: `backend/services/product_request_service.py:474-484` (`get_category_priority`, nested inside `list_timepoint_folders`)
- Test: `tests/unit/test_cr_cross_section_count.py` (extend from Task 1)

**Problem:** `get_category_priority()` checks `"C-R" in n or "CR" in n` (line 481, priority 6) before checking `"CROSS SECTION" in n` (line 483, priority 8). Since `"CROSS SECTION INSPECTION"` starts with `"CR"` (the first two letters of "CROSS"), it always matches the C-R branch first and is sorted into priority 6 alongside the real `6.C-R` folder, never reaching its own priority-8 slot.

**Interfaces:**
- Consumes: nothing new.
- Produces: `list_timepoint_folders`'s returned list is now sorted with `CROSS SECTION INSPECTION` in its own priority-8 slot, distinct from `6.C-R`'s priority-6 slot.

- [ ] **Step 1: Extend the existing test to assert sort order**

In `tests/unit/test_cr_cross_section_count.py`, add a new test function:

```python
def test_cross_section_sorts_separately_from_cr(mock_db):
    """CROSS SECTION INSPECTION must not share the C-R sort bucket."""
    from services.product_request_service import list_timepoint_folders

    conn, cur = mock_db
    cur.fetchall.return_value = [
        ("CROSS SECTION INSPECTION", 12, 0, 99),
        ("6.C-R", 4, 0, 4),
    ]
    cur.fetchone.return_value = (0, 0, 3)

    with patch(
        "services.product_request_service.find_bond_ability_excel",
        return_value=None,
    ):
        folders = list_timepoint_folders("PR2024001", "T0", "MTDQS0906.1")

    names_in_order = [f["name"] for f in folders]
    # 6.C-R (priority 6) must come before CROSS SECTION INSPECTION (priority 8)
    assert names_in_order.index("6.C-R") < names_in_order.index("CROSS SECTION INSPECTION")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest ../tests/unit/test_cr_cross_section_count.py -v -k test_cross_section_sorts_separately`
Expected: FAIL or PASS-by-accident — with only two rows, Python's stable sort keeps insertion order among equal-priority items; since both currently resolve to priority 6, the relative order the mock returns them in (`CROSS...` first, `6.C-R` second) is preserved, so `names_in_order.index("6.C-R") < names_in_order.index("CROSS SECTION INSPECTION")` is FALSE — test fails, confirming the bug.

- [ ] **Step 3: Fix `get_category_priority`**

In `backend/services/product_request_service.py`, change (lines 474-484):

```python
            def get_category_priority(name: str) -> int:
                n = name.upper()
                if "EXTERNAL" in n: return 1
                if "DELAM" in n: return 2
                if "X-RAY" in n or "XRAY" in n: return 3
                if "DECAP" in n: return 4
                if "IMC" in n: return 5
                if "C-R" in n or "CR" in n: return 6
                if "BS,WP,SP" in n: return 7
                if "CROSS SECTION" in n: return 8
                return 99
```

to:

```python
            def get_category_priority(name: str) -> int:
                n = name.upper()
                if "EXTERNAL" in n: return 1
                if "DELAM" in n: return 2
                if "X-RAY" in n or "XRAY" in n: return 3
                if "DECAP" in n: return 4
                if "IMC" in n: return 5
                if "CROSS SECTION" in n: return 8
                if "C-R" in n or "CR" in n: return 6
                if "BS,WP,SP" in n: return 7
                return 99
```

(Moving the `"CROSS SECTION"` check ahead of the `"C-R"`/`"CR"` check is sufficient — no need for a `"CROSS" not in n` guard here since the branches are already mutually exclusive by check order, matching the same fix shape used in Task 1.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest ../tests/unit/test_cr_cross_section_count.py -v`
Expected: PASS (both tests in the file).

- [ ] **Step 5: Run the full suite**

Run: `cd backend && python -m pytest ../tests -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/services/product_request_service.py tests/unit/test_cr_cross_section_count.py
git commit -m "fix: correct CROSS SECTION INSPECTION sort priority vs C-R"
```

---

## Final Verification

- [ ] Run the complete suite one last time: `cd backend && python -m pytest ../tests -v --tb=short`
- [ ] Confirm all 7 spec findings are addressed: grep the diff for `CROSS`, `get_logger`, `_translate_image_path`, `require_role("admin")`, `limiter.limit`, `PIPELINE_COMPOSE_PATH`, and the new `business_domain_requirements.md` section.
- [ ] Manually smoke-test against a running dev server (`python backend/main.py` + `pnpm dev` in `frontend/`) per the spec's "Testing" section: delete-as-non-owner → 403, delete-as-owner → 200, trigger-pipeline-as-non-admin → 403.
