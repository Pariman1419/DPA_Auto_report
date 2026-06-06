# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

DPA is a QA report management system for semiconductor package reliability testing. It generates PowerPoint (PPTX) reports from test data stored in PostgreSQL and images from a Windows file share. The system has two sub-projects:

- **`backend/`** — FastAPI (Python) REST API, port 9090
- **`frontend/`** — React + Vite + Tailwind SPA, port 5190

## Development Commands

### Backend

```powershell
cd backend
# Activate virtualenv (Windows)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt   # if requirements.txt exists
# or install manually: fastapi uvicorn psycopg2-binary oracledb python-jose bcrypt python-dotenv slowapi itsdangerous pillow python-pptx

# Run dev server (auto-reload)
python main.py
# or: uvicorn main:app --reload --port 9090
```

### Frontend

```powershell
cd frontend
pnpm install   # uses pnpm (pnpm-lock.yaml present)
pnpm dev       # starts Vite dev server on port 5190
pnpm build     # production build
```

Vite proxies `/api/*` → `http://localhost:9090`, so frontend and backend must both be running in development.

## Environment Variables

Copy `backend/.env` and set real values before starting. Required vars that cause `sys.exit(1)` if missing:

| Variable | Purpose |
|---|---|
| `DB_HOST` | PostgreSQL host (10.151.28.2 in dev) |
| `DB_USER` | PostgreSQL username |
| `DB_PASSWORD` | PostgreSQL password |
| `JWT_SECRET_KEY` | JWT signing secret — change in production |

Optional but important:

| Variable | Default | Purpose |
|---|---|---|
| `DB_NAME` | `DPA` | PostgreSQL database name |
| `DB_PORT` | `5432` | PostgreSQL port |
| `DOC_ROOT` | `D:\DPA\doc` | Root for PR Excel files |
| `TEMPLATE_PATH` | `D:\DPA\Template\DPA report.pptx` | PPTX report template |
| `OUTPUT_DIR` | `D:\DPA\output` | Where generated reports are saved |
| `IMAGE_WIN_ROOT` | `D:\Auto_detect\Result` | Path prefix stored in DB |
| `IMAGE_MOUNT_ROOT` | same as `IMAGE_WIN_ROOT` | Where that path is mounted locally |
| `ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated CORS origins |
| `COOKIE_SECURE` | `false` | Set `true` in HTTPS production |
| `SMTP_HOST`, `SMTP_PORT`, `APPROVER_EMAIL`, `SENDER_EMAIL`, `BASE_URL` | — | Email for user approval workflow |

## Architecture

### Backend

```
backend/
  main.py                        # FastAPI app wiring: CORS, rate limiter, routers
  logger.py                      # Centralised logging (console + rotating file at logs/)
  models/schemas.py              # Pydantic models for all request/response bodies
  routers/
    auth.py                      # /api/auth/* — login, logout, register, approve
    product_request.py           # /api/* — PR data, report generation, image serving
  services/
    auth_service.py              # bcrypt password hashing, JWT create/decode
    db_connector.py              # psycopg2 connection pool (PostgreSQL) + oracledb (Oracle DW)
    product_request_service.py   # DB queries for PR metadata, lots, timepoints, image lists
    report_generator.py          # DPAReportGenerator — fills PPTX template with data + images
```

**Auth flow:** JWT stored as `httpOnly` cookie (`dpa_token`). Bearer header is a fallback. `get_current_user` dependency validates both. New users register with `is_active=False`; admin receives a time-limited email link to approve.

**Report generation flow:** `POST /api/generate-report` → `DPAReportGenerator` fetches PR metadata and image paths from PostgreSQL, translates Windows DB paths to local mount paths, fills the PPTX template slide-by-slide, writes output to `OUTPUT_DIR`, and records the run in `generation_history`.

**Path translation:** Image paths stored in the DB use a Windows prefix (`IMAGE_WIN_ROOT`). `_translate_image_path()` in both `product_request_service.py` and `report_generator.py` rewrites them to `IMAGE_MOUNT_ROOT` for cross-environment compatibility.

**Database:** PostgreSQL at `DB_HOST`. Key tables: `requests`, `info_requirements`, `background_info`, `bill_of_materials`, plus tables for test steps and generation history. An optional Oracle Datawarehouse connection exists for `DW_*` vars.

### Frontend

```
frontend/src/
  main.jsx          # React root mount
  App.jsx           # Root component: auth gate, page routing (create/history/dashboard)
  api.js            # apiFetch() wrapper — sends credentials, handles 401 redirect; user profile in localStorage
  Sidebar.jsx       # Navigation
  LoginPage.jsx     # Login form
  RegisterPage.jsx  # Registration form
  CreateReport.jsx  # 3-step wizard: Select PR → Verify data → Generate PPTX
  HistoryPage.jsx   # Past generation records with download/delete
  Components.jsx    # Shared UI primitives (Btn, Card, CalSans, etc.)
  ErrorStates.jsx   # Error display components
```

**UI stack:** React 18, MUI v7, Radix UI primitives, Tailwind CSS v4, Recharts, pptxgenjs (client-side PPTX for previews), react-hook-form, react-router v7.

**Auth:** `apiFetch()` always sends `credentials: 'include'` so the cookie is forwarded. The user profile object (non-sensitive) is cached in `localStorage`. A `_redirecting` guard prevents redirect storms on concurrent 401s.

## Key Conventions

- All backend modules call `from logger import get_logger` — never use `print()` in production code.
- Rate limiting is applied at the router level via `@limiter.limit("5/minute")` — add it to any new sensitive endpoint.
- Path security: file-serving endpoints (`/api/image`, `/api/download-report`) always resolve the requested path and assert it is within an allowed root before serving.
- The `require_role(*roles)` dependency factory in `auth.py` is the standard way to gate endpoints by role.
