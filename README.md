# DPA Auto Report — QA Reliability Report Generator

> A full-stack web application that automates PowerPoint (PPTX) report generation for
> **semiconductor package reliability testing (DPA — Destructive Physical Analysis)**.
> It pulls test data from PostgreSQL and inspection images (produced by the AI
> [Auto_detect](https://github.com/Pariman1419/Auto_detect) pipeline) from a file share, then
> fills a corporate PPTX template slide-by-slide — turning a multi-hour manual reporting task
> into a few clicks.

<p align="left">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="React" src="https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black">
  <img alt="Vite" src="https://img.shields.io/badge/Vite-646CFF?logo=vite&logoColor=white">
  <img alt="PostgreSQL" src="https://img.shields.io/badge/PostgreSQL-4169E1?logo=postgresql&logoColor=white">
  <img alt="Docker" src="https://img.shields.io/badge/Docker-2496ED?logo=docker&logoColor=white">
</p>

---

## ✨ Highlights

- **Automated PPTX generation** — `python-pptx` fills a real corporate template with metadata,
  test results, and inspection images, then records every run in a generation-history table.
- **Secure auth** — JWT in an `httpOnly` cookie (Bearer-header fallback), bcrypt password
  hashing, role-based access control, and an email-based admin approval workflow for new users.
- **Hardened file serving** — every image / download endpoint resolves the requested path and
  asserts it stays inside an allowed root (path-traversal protection), plus per-route rate limiting.
- **Cross-environment path translation** — DB-stored Windows image paths are rewritten to the
  local mount root at runtime so the same data works in dev and production.
- **Dual data sources** — primary PostgreSQL plus an optional Oracle Datawarehouse connection.
- **Modern React UI** — a 3-step wizard (Select PR → Verify data → Generate) built with MUI v7,
  Radix UI, Tailwind v4, and Recharts, with client-side PPTX previews via `pptxgenjs`.

## 🏗️ Architecture

```
┌──────────────────┐        /api/*        ┌────────────────────────┐
│  React + Vite    │ ───────────────────► │  FastAPI (Python)      │
│  SPA  :5190      │  (cookie auth)       │  REST API  :9090       │
└──────────────────┘ ◄─────────────────── └───────────┬────────────┘
                                                       │
                       ┌───────────────────────────────┼───────────────────────┐
                       ▼                                ▼                       ▼
              ┌─────────────────┐            ┌────────────────────┐   ┌──────────────────┐
              │ PostgreSQL (DPA)│            │ python-pptx engine │   │ Image file share │
              │ requests, BOM,  │            │ fills PPTX template│   │ (inspection imgs)│
              │ test steps …    │            │ → output/*.pptx    │   └──────────────────┘
              └─────────────────┘            └────────────────────┘
```

### Backend (`backend/`) — FastAPI, port 9090
| Module | Responsibility |
|---|---|
| `main.py` | App wiring: CORS, rate limiter, routers |
| `routers/auth.py` | Login, logout, register, admin approval |
| `routers/product_request.py` | PR data, report generation, image serving |
| `services/auth_service.py` | bcrypt hashing, JWT create/decode |
| `services/db_connector.py` | psycopg2 pool (PostgreSQL) + oracledb (Oracle DW) |
| `services/product_request_service.py` | PR metadata, lots, timepoints, image lists |
| `services/report_generator.py` | `DPAReportGenerator` — fills the PPTX template |

### Frontend (`frontend/`) — React + Vite, port 5190
| File | Responsibility |
|---|---|
| `App.jsx` | Auth gate + page routing |
| `api.js` | `apiFetch()` wrapper (credentials, 401 handling) |
| `CreateReport.jsx` | 3-step report-generation wizard |
| `HistoryPage.jsx` | Past runs with download / delete |
| `Components.jsx` | Shared UI primitives |

## 🛠️ Tech Stack

**Backend:** FastAPI · Uvicorn · psycopg2 · oracledb · python-pptx · Pillow · python-jose (JWT) · bcrypt · slowapi · openpyxl
**Frontend:** React 18 · Vite · MUI v7 · Radix UI · Tailwind CSS v4 · Recharts · pptxgenjs · react-hook-form · react-router v7
**Infra:** PostgreSQL · Oracle DW (optional) · Docker / docker-compose · Nginx (frontend serve)

## 🚀 Getting Started

### Prerequisites
- Python 3.11+, Node 18+ with `pnpm`, and a reachable PostgreSQL instance.

### 1. Backend
```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# configure environment
copy .env.example .env   # then edit .env with real values

python main.py           # starts on http://localhost:9090
```

### 2. Frontend
```powershell
cd frontend
pnpm install
pnpm dev                 # starts on http://localhost:5190
```
Vite proxies `/api/*` → `http://localhost:9090`, so run both during development.

### 3. Docker (optional)
```powershell
docker-compose up --build
```

## ⚙️ Configuration

All backend config lives in `backend/.env` (see `backend/.env.example`). Variables that cause
startup to abort if missing: `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `JWT_SECRET_KEY`.

> 🔒 **Security note:** the real `.env` is gitignored and never committed. Only `.env.example`
> with placeholder values ships in the repo.

## 📁 Project Structure

```
DPA/
├── backend/        FastAPI REST API
│   ├── routers/    auth + product-request endpoints
│   ├── services/   DB connector, auth, report generator
│   ├── models/     Pydantic schemas
│   └── main.py
├── frontend/       React + Vite SPA
│   └── src/        pages + shared components
├── docs/           additional design & architecture docs
├── schema.sql      database schema
└── docker-compose.yml
```

## 🔄 End-to-End Workflow (two separate systems)

This repo is **System 2** of a two-part platform. The systems are decoupled and communicate only
through a **shared PostgreSQL database + image file share** — each can be deployed and run
independently.

```
╔════════ SYSTEM 1 · Auto_detect (separate repo) ════════╗
║  Raw inspection images (doc/)                          ║
║     → FastSAM AI segmentation + OCR                     ║
║     → crop ROI, extract measurements                   ║
║     → write Result/ (images + JSON)                    ║
╚═══════════════════════╤════════════════════════════════╝
                        │ writes
                        ▼
              ┌───────────────────────┐
              │  PostgreSQL  +  image │   ← shared boundary
              │  file share (Result/) │
              └───────────┬───────────┘
                        │ reads
                        ▼
╔════════ SYSTEM 2 · DPA Auto Report (THIS REPO) ════════╗
║  React wizard: select PR → verify data → generate      ║
║     → FastAPI fetches PR metadata + image paths        ║
║     → python-pptx fills the template slide-by-slide    ║
║     → download .pptx  +  log to generation_history     ║
╚════════════════════════════════════════════════════════╝
```

## 🔗 Related project

- **[Auto_detect — AI DPA Image Extraction Pipeline](https://github.com/Pariman1419/Auto_detect)**
  is the upstream data engine (System 1 above) that produces the images and measurements this
  report generator consumes.

## 📄 License

This project is shared for portfolio / demonstration purposes.

---

<sub>Built by <b>Pariman</b> — full-stack application for automating QA reliability reporting in semiconductor manufacturing.</sub>
