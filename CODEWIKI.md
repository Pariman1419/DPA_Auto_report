# DPA System — Codewiki

> Generated: 2026-05-06  
> Covers: `D:\DPA` (web application) and `D:\Auto_detect` (ETL pipeline)

---

## Table of Contents

1. [System Architecture Overview](#1-system-architecture-overview)
2. [Data Flow Diagram](#2-data-flow-diagram)
3. [D:\Auto_detect — ETL Pipeline](#3-dauto_detect--etl-pipeline)
   - 3.1 [auto_pipeline.py — Orchestrator](#31-auto_pipelinepy--orchestrator)
   - 3.2 [scripts/excel_reader.py](#32-scriptsexcel_readerpy)
   - 3.3 [scripts/ext_visual.py](#33-scriptsext_visualpy)
   - 3.4 [scripts/ext_delam.py](#34-scriptsext_delampy)
   - 3.5 [scripts/ext_xray.py](#35-scriptsext_xraypy)
   - 3.6 [scripts/ext_decap.py](#36-scriptsext_decappy)
   - 3.7 [scripts/ext_imc.py](#37-scriptsext_imcpy)
   - 3.8 [scripts/ext_C_R.py](#38-scriptsext_c_rpy)
   - 3.9 [scripts/ext_sem.py](#39-scriptsext_sempy)
   - 3.10 [scripts/ext_bonds.py](#310-scriptsext_bondspy)
   - 3.11 [scripts/db_connector.py](#311-scriptsdb_connectorpy)
   - 3.12 [scripts/setup_new_tables.py / reset_db.py](#312-scriptssetup_new_tablespy--reset_dbpy)
4. [D:\DPA — Web Application](#4-ddpa--web-application)
   - 4.1 [Backend Overview (FastAPI)](#41-backend-overview-fastapi)
   - 4.2 [main.py / app entry point](#42-mainpy--app-entry-point)
   - 4.3 [models/schemas.py](#43-modelsschemasspy)
   - 4.4 [services/db_connector.py](#44-servicesdb_connectorpy)
   - 4.5 [services/auth_service.py](#45-servicesauth_servicepy)
   - 4.6 [services/product_request_service.py](#46-servicesproduct_request_servicepy)
   - 4.7 [services/report_generator.py](#47-servicesreport_generatorpy)
   - 4.8 [routers/auth.py](#48-routersauthpy)
   - 4.9 [routers/product_request.py](#49-routersproduct_requestpy)
   - 4.10 [Frontend (React + Vite)](#410-frontend-react--vite)
5. [PostgreSQL Database Schema](#5-postgresql-database-schema)
6. [Cross-System Integration Points](#6-cross-system-integration-points)
7. [Image Path Conventions](#7-image-path-conventions)
8. [Report Generation — Placeholder System](#8-report-generation--placeholder-system)
9. [Known Issues & Critical Gotchas](#9-known-issues--critical-gotchas)

---

## 1. System Architecture Overview

```
D:\Auto_detect (ETL / Preprocessing)
    Input:  D:\Auto_detect\doc\<PR>\<Timepoint>\<Lot>\<Category>\  (raw images + Excel)
    Output: D:\Auto_detect\Result\<PR>\images\<TP>\<Lot>\<Category>\  (processed images)
            D:\Auto_detect\Result\<PR>\data_ready\*.json             (metadata)
    Action: Writes processed data to PostgreSQL @ 10.151.28.2:5432/DPA

                          PostgreSQL
                     (10 normalized tables)
                          ↑           ↓
               D:\Auto_detect     D:\DPA\backend
               (writes data)      (reads data → PPTX)

D:\DPA (Web Application)
    Backend:  FastAPI  → serves JSON API on :8000
    Frontend: React+Vite → served via Vite dev server or built static
    Template: D:\DPA\Template\DPA report.pptx
    Output:   D:\DPA\output\*.pptx
```

---

## 2. Data Flow Diagram

```
Excel File (.xlsx)
       │
       ▼
excel_reader.read_product_request(pr)
       │  returns ProductRequestData (Pydantic)
       ▼
auto_pipeline.run_pipeline()
       │
       ├─ For each Timepoint / Lot:
       │     ├─ ext_visual   → 1.EXTERNAL VISUAL images
       │     ├─ ext_delam    → 2.DELAM images
       │     ├─ ext_xray     → 3.X-RAY images
       │     ├─ ext_decap    → 4.DECAP images
       │     ├─ ext_imc      → 5.IMC images + imc_summary.txt
       │     ├─ ext_C_R      → 6.C-R images
       │     ├─ ext_sem      → CROSS SECTION INSPECTION images + sem_data.json
       │     └─ ext_bonds    → 7.BS,WP,SP images + BOND_ABILITY_REPORT.xlsx
       │
       ▼
import_to_db(pr_result_dir, metadata)
       │  Upserts to all 10 PostgreSQL tables
       ▼
PostgreSQL DPA database
       │
       ▼ (on report request)
DPAReportGenerator.generate()
       │  fetch_full_report_data() → all tables
       │  Open template PPTX
       │  Replace text placeholders: {table.column_key}
       │  Replace image placeholders: insert actual images
       ▼
D:\DPA\output\DPA_Report_<PR>_<TP>_<Lot>_<timestamp>.pptx
```

---

## 3. D:\Auto_detect — ETL Pipeline

### Directory Layout

```
D:\Auto_detect\
├── auto_pipeline.py          # Main orchestrator
├── scripts\
│   ├── db_connector.py       # PostgreSQL connection (shared)
│   ├── excel_reader.py       # Parse Excel → ProductRequestData
│   ├── ext_visual.py         # Extract EXTERNAL VISUAL images
│   ├── ext_delam.py          # Extract DELAM images
│   ├── ext_xray.py           # Extract X-RAY images
│   ├── ext_decap.py          # Extract DECAP images
│   ├── ext_imc.py            # Extract IMC images + measurements
│   ├── ext_C_R.py            # Extract C-R images
│   ├── ext_sem.py            # Extract SEM / Cross Section images
│   ├── ext_bonds.py          # Extract Bond pull/shear data
│   ├── setup_new_tables.py   # DDL: create tables
│   └── reset_db.py           # DDL: drop & recreate
├── doc\                      # Raw input: <PR>\<TP>\<Lot>\<Category>
├── Result\                   # Processed output
│   └── <PR>\
│       ├── images\<TP>\<Lot>\<Category>\   (processed images)
│       └── data_ready\                     (JSON/TXT metadata)
└── Template\
    └── BOND ABILITY TEST.xlsx
```

### 3.1 auto_pipeline.py — Orchestrator

**Entry point:** `run_pipeline()`  
**Key logic:**

1. Iterates `doc/<PR>` folders
2. Calls `excel_reader.read_product_request(pr)` → Pydantic model → `metadata` dict
3. Iterates timepoints and lots under each PR
4. Uses `find_path_case_insensitive(base, name)` for flexible folder matching (e.g. `"5.IMC"` matches `"5. IMC"` or `"5.IMC_NEW"`)
5. Calls each `ext_*.py` processor in order
6. Calls `import_to_db(pr_result_dir, metadata)` after all extraction

**`import_to_db(pr_path, meta)` — Database writer:**

- Upserts `requests` (ON CONFLICT DO UPDATE)
- Deletes old rows from 8 child tables before re-inserting
- Inserts: `info_requirements`, `background_info`, `bill_of_materials`, `reliability_tests`, `test_cases`
- Walks `Result/<PR>/images/<TP>/<Lot>/` per category:
  - `imc_measurements` — reads from `imc_summary_<TP>_<Lot>.txt`
  - `image_records` — walks ALL image files, stores absolute path + category name
  - `bond_measurements` — reads from `BOND_ABILITY_REPORT.xlsx`
  - `sem_records` — reads from `sem_data_<TP>_<Lot>.json`, stores absolute path

**Critical:** `sem_records.file_path` stores absolute path like:
```
D:\Auto_detect\Result\<PR>\images\<TP>\<Lot>\CROSS SECTION INSPECTION\U1\<name>_SEM.jpg
```

### 3.2 scripts/excel_reader.py

Parses the Excel `.xlsx` file from `doc/<PR>/` and returns a `ProductRequestData` Pydantic model.  
Also provides `list_timepoints(pr)` which reads column headers to discover timepoints (T0, T1, T2, etc.).

### 3.3 scripts/ext_visual.py

- Input: `1.EXTERNAL VISUAL` folder
- Uses OpenCV for contour/edge detection (Canny, Otsu threshold)
- Outputs processed images to Result folder
- Category stored in DB as `"1.EXTERNAL VISUAL"`

### 3.4 scripts/ext_delam.py

- Input: `2.DELAM` folder
- Delamination analysis via OpenCV
- Category stored as `"2.DELAM"`

### 3.5 scripts/ext_xray.py

- Input: `3.X-RAY` folder
- X-ray image processing
- Category stored as `"3.X-RAY"`

### 3.6 scripts/ext_decap.py

- Input: `4.DECAP` folder
- Decapsulation image processing
- Category stored as `"4.DECAP"`

### 3.7 scripts/ext_imc.py

- Input: `5.IMC` folder
- IMC (Intermetallic Compound) measurement extraction
- Uses Tesseract OCR fallback to detect IMC percentage values
- Outputs `imc_summary.txt` in the Result folder (then moved to `data_ready/`)
- Category stored as `"5.IMC"`

### 3.8 scripts/ext_C_R.py

- Input: `6.C-R` folder
- Cross-section / Reliability image extraction
- Category stored as `"6.C-R"`

### 3.9 scripts/ext_sem.py

Key functions:

**`parse_sem_txt(txt_path)`**  
Reads `.txt` metadata files alongside SEM images. Extracts:
- `$CM_MAG` → magnification (e.g. `"500"`)
- `$CM_ACCEL_VOLT` → acceleration voltage (e.g. `"15.0"`)

**`check_image_for_measurement(image_path)`**  
OCR fallback: detects green "um" scale text in SEM images using Tesseract.

**`process_sem_folder(input_dir, output_dir)`**  
- Walks input directory for U-prefixed subfolders (U1, U2, U3, etc.)
- Prefers hyphen-named files (e.g. `B1-1.tif`)
- Copies as `{name}_SEM.jpg` to output
- Returns list of dicts:
  ```python
  {"unit_id": "U1", "point_id": "B1-1", "magnification": "500",
   "accel_volt": "15.0", "rel_path": "U1/B1-1_SEM.jpg"}
  ```
- Stored in `data_ready/sem_data_<TP>_<Lot>.json`

### 3.10 scripts/ext_bonds.py

- Input: `7.BS,WP,SP` folder (also handles `7.BS,WS,SP`)
- Bond pull / shear / wire pull measurements
- Generates `BOND_ABILITY_REPORT.xlsx` in output folder
- Data inserted into `bond_measurements` table

### 3.11 scripts/db_connector.py (Auto_detect version)

```python
class DBConnector:
    @classmethod
    def get_connection(cls):   # Returns raw psycopg2 connection (no pool)
    @classmethod
    def release_connection(cls, conn): # conn.close()
```

Uses the same PostgreSQL host (`10.151.28.2:5432/DPA`) but different class from DPA backend's pooled connector.

### 3.12 scripts/setup_new_tables.py / reset_db.py

DDL scripts. `setup_new_tables.py` creates tables if missing. `reset_db.py` drops and recreates all tables (destructive — use with care).

---

## 4. D:\DPA — Web Application

### Directory Layout

```
D:\DPA\
├── backend\
│   ├── main.py                      # FastAPI app entry
│   ├── models\
│   │   └── schemas.py               # Pydantic request/response models
│   ├── services\
│   │   ├── db_connector.py          # Pooled PostgreSQL + Oracle DW
│   │   ├── auth_service.py          # JWT + bcrypt
│   │   ├── product_request_service.py  # DB queries + preview helpers
│   │   └── report_generator.py      # PPTX generation engine
│   ├── routers\
│   │   ├── auth.py                  # /api/login, /api/logout, /api/register
│   │   └── product_request.py       # All /api/* report endpoints
│   └── test_report_real.py          # Manual test script
├── frontend\
│   └── src\
│       ├── App.jsx
│       ├── CreateReport.jsx         # Main 3-step wizard UI
│       ├── Dashboard.jsx
│       ├── History.jsx
│       └── ...
├── Template\
│   └── DPA report.pptx              # PPTX template with placeholders
└── output\                          # Generated reports
```

### 4.1 Backend Overview (FastAPI)

- Framework: FastAPI with Uvicorn
- Auth: JWT tokens stored in httpOnly cookies
- DB: psycopg2 ThreadedConnectionPool (1–10 connections)
- Port: 8000 (default)

### 4.2 main.py / app entry point

Registers routers:
```python
app.include_router(auth_router)
app.include_router(product_request_router)
```

CORS configured for frontend dev server origin.

### 4.3 models/schemas.py

Pydantic models used for request/response validation:

| Model | Purpose |
|-------|---------|
| `BackgroundInfo` | Customer, package, requestor info |
| `BillOfMaterial` | Lot, device, materials |
| `TestStep` | Individual test case step |
| `ReliabilityTest` | Reliability test with steps |
| `ProductRequestData` | Full PR data (root model) |
| `ProductRequestListItem` | Lightweight list view |
| `GenerateReportRequest` | Report generation parameters |
| `LoginRequest / LoginResponse` | Auth |
| `RegisterRequest` | User registration |
| `TokenResponse` | JWT response |

### 4.4 services/db_connector.py

```python
class DBConnector:
    _dpa_pool = None  # psycopg2.pool.ThreadedConnectionPool(1, 10)

    get_dpa_connection()     # Returns pooled PostgreSQL connection
    release_dpa_connection() # Returns connection to pool
    get_dw_connection()      # Oracle DW (oracledb) — used for DW lookups
```

Environment variables:
- `DB_HOST` → `10.151.28.2`
- `DB_PORT` → `5432`
- `DB_NAME` → `DPA`
- `DB_USER` → `postgres`
- `DB_PASSWORD` → (required, no default)
- `DW_USER/DW_PASSWORD/DW_DSN` → Oracle DW credentials

### 4.5 services/auth_service.py

- Password hashing: bcrypt
- Token creation: HS256 JWT, 24-hour expiry
- Token storage: httpOnly cookie `"access_token"`
- `get_current_user()` dependency validates JWT on every protected endpoint

### 4.6 services/product_request_service.py

**Core functions:**

| Function | Purpose |
|----------|---------|
| `list_product_requests()` | Returns all PR numbers + folder names |
| `read_product_request(pr_no)` | Full metadata for one PR (Pydantic model) |
| `list_lots(pr_no)` | Lots for a PR |
| `list_timepoints(pr_no, lot)` | Timepoints for a PR/Lot |
| `list_timepoint_folders(pr_no, tp, lot)` | Category folders with file counts |
| `get_next_revision(pr_no, tp)` | Next revision letter (A→B→...→AA) |
| `fetch_full_report_data(pr_no, lot, tp)` | All DB data for report generation |
| `save_generation_history(...)` | Records a generated report |
| `list_generation_history()` | Returns generation history |
| `get_history_record(record_id)` | Single history record |
| `delete_history_record(record_id)` | Delete + optionally remove file |
| `get_generation_stats()` | Dashboard counts |
| `list_preview_images(...)` | Image file list for a category |
| `list_preview_imc(...)` | IMC measurements preview |
| `list_preview_bond(...)` | Bond measurements preview |
| `list_preview_sem(...)` | SEM records preview (unit_id, point_id, mag, accel_volt, file_path) |
| `find_bond_ability_excel(...)` | Locate BOND_ABILITY_REPORT.xlsx |

**Critical Bug Fix (line 211):**  
`RealDictCursor` returns dict rows — access by column name, NOT integer index.
```python
# WRONG (crashes with KeyError: 0)
lot_base = os.path.dirname(os.path.dirname(sample[0]))
# CORRECT
lot_base = os.path.dirname(os.path.dirname(sample["file_path"]))
```

**`fetch_full_report_data` return structure:**
```python
{
    "metadata":         dict,           # PR header info
    "bom":              dict,           # Bill of materials
    "reliability_tests": list[dict],
    "imc_measurements": list[dict],
    "image_records":    list[dict],     # All images by category
    "bond_measurements": list[dict],
    "sem_records":      list[dict],     # Cross Section Inspection
}
```

### 4.7 services/report_generator.py

**Class: `DPAReportGenerator`**

Constructor: `(pr_number, timepoint, lot, selected_sections, revision="A")`

**`generate()` workflow:**
1. `load_data()` — fetches DB data + opens PPTX template
2. Identify slides by category tag
3. Delete slides for unselected sections (reverse order to preserve indices)
4. `_process_slide(slide)` — for each remaining slide:
   - Scan all text frames for `{table.key}` placeholders
   - Replace text placeholders with DB values
   - Replace image placeholders with actual images (inline)
5. Save to `OUTPUT_DIR/DPA_Report_<PR>_<TP>_<Lot>_<timestamp>.pptx`

**`IMAGE_SIZE_CONFIG` (width_in × height_in × margin_in):**

| Key | Width | Height | Margin | Category |
|-----|-------|--------|--------|---------|
| `EXTERANAL` | auto | auto | auto | External Visual |
| `XRAY` | 1.10" | 1.10" | 0.03" | X-Ray |
| `DELAM` | 2.80" | 1.30" | 0.02" | Delamination |
| `DECAP` | 1.30" | 1.06" | 0.02" | Decap |
| `IMC` | 0.90" | 0.90" | 0.02" | IMC |
| `C-R` | 0.90" | 0.90" | 0.02" | Cross-section/Reliability |
| `IMAGE` | 1.50" | 2.00" | 0.02" | **SEM / Cross Section** |
| `UNIT` | 0.90" | 0.90" | 0.02" | Unit images |
| `BS` | auto | auto | auto | Bond shear |

**Placeholder format:**
```
{table_name.column_key}
```
Examples:
- `{background_info.customer_name}` — text replacement
- `{sem_records.image_2_B1-1}` — image replacement
  - `table` = `sem_records`, `clean_key` = `image_2_B1-1`
  - Size key derived: `clean_key.upper().split("_")[0]` = `"IMAGE"` → 1.50" × 2.00"

**`_find_image_path(key)` column detection order:**
```python
for c in ["magnification", "accel_volt", "unit_id", "point_id", "file_path", "image"]:
    if c in p_clean:
        col = c; break
```
For `image_2_B1-1`: matches `"image"` → queries `sem_records` by point_id `"B1-1"` → returns file_path.

**`_CATEGORY_MAP`** maps abbreviated section names to full DB categories:
```python
{
    "EXTERANAL": "1.EXTERNAL VISUAL",
    "DELAM":     "2.DELAM",
    "XRAY":      "3.X-RAY",
    "DECAP":     "4.DECAP",
    "IMC":       "5.IMC",
    "C-R":       "6.C-R",
    "CR":        "6.C-R",
    "UNIT":      "7.BS,WP,SP",
    "BS":        "7.BS,WP,SP",
}
```
Note: `"IMAGE"` is **not** in `_CATEGORY_MAP` — SEM images are fetched directly from `sem_records` table, not via `image_records`.

### 4.8 routers/auth.py

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/login` | POST | Validates credentials, sets JWT cookie |
| `/api/logout` | POST | Clears JWT cookie |
| `/api/register` | POST | Creates new user |
| `/api/me` | GET | Returns current user info |

`get_current_user` dependency used by all protected routes.

### 4.9 routers/product_request.py

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/stats` | GET | Dashboard statistics |
| `/api/history` | GET | Generation history |
| `/api/history/{id}/download` | GET | Download generated PPTX |
| `/api/history/{id}` | DELETE | Delete history record |
| `/api/product-requests` | GET | List all PRs |
| `/api/product-request/{pr}` | GET | Full PR metadata |
| `/api/product-request/{pr}/lots` | GET | Available lots |
| `/api/product-request/{pr}/timepoints` | GET | Available timepoints |
| `/api/product-request/{pr}/{tp}/folders` | GET | Category folders |
| `/api/product-request/{pr}/{tp}/next-revision` | GET | Next revision letter |
| `/api/generate-report` | POST | Trigger PPTX generation |
| `/api/download-report` | GET | Download by file path (security: path must be inside OUTPUT_DIR or Result) |
| `/api/bond-excel-path` | GET | Path to BOND_ABILITY_REPORT.xlsx |
| `/api/product-request/{pr}/{tp}/{lot}/preview-images` | GET | Preview images for a category |
| `/api/product-request/{pr}/{tp}/{lot}/preview-imc` | GET | Preview IMC data |
| `/api/product-request/{pr}/{tp}/{lot}/preview-bond` | GET | Preview bond data |
| `/api/product-request/{pr}/{tp}/{lot}/preview-sem` | GET | Preview SEM/cross section data |
| `/api/image` | GET | Serve image file (restricted to `D:\Auto_detect\Result`) |

### 4.10 Frontend (React + Vite)

**Key components:**

| File | Purpose |
|------|---------|
| `App.jsx` | Router, auth guard, layout |
| `Dashboard.jsx` | Stats cards + quick actions |
| `CreateReport.jsx` | 3-step report wizard |
| `History.jsx` | Past reports table + download |

**CreateReport.jsx — 3-step wizard:**

1. **Step 1: Select PR** — dropdown of product requests
2. **Step 2: Configure** — select Lot, Timepoint, sections; preview category folders
   - `SectionPreviewItem` component: expandable per-category preview
   - For CROSS SECTION INSPECTION: fetches `/api/.../preview-sem` → groups by `unitId` → renders U1, U2 cards (U3 filtered out)
   - For other categories: fetches preview-images, preview-imc, preview-bond
3. **Step 3: Generate** — triggers `/api/generate-report`, shows stats, download link

**apiFetch wrapper:** Handles auth headers and base URL prefix.

**Image display:** `<img src={/api/image?path=...}` for all preview thumbnails.  
Fullscreen modal on click via `setFullscreenImage`.

---

## 5. PostgreSQL Database Schema

**Host:** `10.151.28.2:5432/DPA`  
**Tables (10 total):**

```sql
requests            (pr_no PK, customer_name, order_lot, excel_file_name, pr_revision, created_at)
info_requirements   (id, pr_no FK, folder_name, subject, purpose, request_date, conclusion, summary_json, created_at)
background_info     (id, pr_no FK, customer_name, assembly_site, package_type, date_code,
                     package_size, number_of_lot, pin_ball_count, requestor_name_dept,
                     reliability_staff_name, rel_request_number::jsonb, created_at)
bill_of_materials   (id, pr_no FK, order_lot, cust_assy, device, die_size, dap_size,
                     lf_stock_no, die_attach_material, wire_type, mold_compound, plating_finish, created_at)
reliability_tests   (id, pr_no FK, lot_name, rel_name, duration, test_condition, sample_size, created_at)
test_cases          (id, rel_test_id FK, pr_no, lot_name, name, duration, test_condition,
                     sample_size, result, plan_start, plan_finish, status, created_at)
imc_measurements    (id, pr_no FK, lot_name, timepoint, unit_id, imc_value, created_at)
image_records       (id, pr_no FK, lot_name, timepoint, category, file_name, file_path, created_at)
bond_measurements   (id, pr_no FK, lot_name, timepoint, test_type, unit_id, value, created_at)
sem_records         (id, pr_no FK, lot_name, timepoint, unit_id, point_id, magnification,
                     accel_volt, file_path, created_at)
generation_history  (id, pr_no, lot, revision, timepoint, user_id, file_name, file_path, created_at)
users               (id, user_id, full_name, password_hash, email, role, created_at)
```

**Key distinction:**
- `image_records` — ALL image files from ALL categories (including `CROSS SECTION INSPECTION`)
- `sem_records` — SEM-specific records with structured metadata (unit_id, point_id, mag, accel_volt)
- Report generator uses `sem_records` for `{sem_records.*}` placeholders, NOT `image_records`

---

## 6. Cross-System Integration Points

### Shared Database

Both systems connect to the same PostgreSQL instance:
- `D:\Auto_detect\scripts\db_connector.py` — raw psycopg2, no pooling
- `D:\DPA\backend\services\db_connector.py` — ThreadedConnectionPool(1, 10)

### Shared File Paths

Images produced by `D:\Auto_detect` are referenced by absolute paths in the database.  
`D:\DPA\backend` reads those absolute paths to serve images and generate reports.

The API endpoint `/api/image?path=...` enforces that served paths start with `D:\Auto_detect\Result`.

The endpoint `/api/download-report?path=...` allows paths in `D:\DPA\output` OR `D:\Auto_detect\Result`.

### Timepoint Normalization

DB may store timepoints as `"T0"` or `"- T0"` depending on the source.  
`list_preview_sem` handles this with:
```sql
WHERE (timepoint = %s OR LTRIM(timepoint, '- ') = %s)
```

---

## 7. Image Path Conventions

### Source (raw input)
```
D:\Auto_detect\doc\<PR>\<Timepoint>\<Lot>\<Category>\<files>
```

### Processed output
```
D:\Auto_detect\Result\<PR>\images\<Timepoint>\<Lot>\<Category>\<files>
```

### SEM specific
```
D:\Auto_detect\Result\<PR>\images\<Timepoint>\<Lot>\CROSS SECTION INSPECTION\<UnitId>\<name>_SEM.jpg
```

### Stored in DB (sem_records.file_path)
Absolute path, e.g.:
```
D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\CROSS SECTION INSPECTION\U1\B1-1_SEM.jpg
```

---

## 8. Report Generation — Placeholder System

### Text Placeholders

Pattern: `{table_name.column_name}`  
Example: `{background_info.customer_name}`

Resolved by looking up `table_name` in `data["table_name"]` list and finding matching column.

### Image Placeholders

Pattern: `{sem_records.image_<index>_<point_id>}`  
Example: `{sem_records.image_2_B1-1}`

Resolution steps:
1. Detect `"image"` in `clean_key` → query `sem_records`
2. Extract `point_id` from key suffix (after last `_`)
3. Query `sem_records WHERE pr_no=? AND lot=? AND timepoint=? AND point_id=?`
4. Return `file_path` from the matched row
5. Insert image at placeholder position with size from `IMAGE_SIZE_CONFIG["IMAGE"]` = (1.50", 2.00")

### Section Selection

Selected sections must match **exact DB category names**:
```python
{
    "1.EXTERNAL VISUAL": True,
    "2.DELAM": True,
    "3.X-RAY": True,
    "4.DECAP": True,
    "5.IMC": True,
    "6.C-R": True,
    "7.BS,WP,SP": True,
}
```

---

## 9. Known Issues & Critical Gotchas

### 1. RealDictCursor — No Integer Index Access

`psycopg2.extras.RealDictCursor` returns `RealDictRow` objects. These are **dicts**, not tuples.  
**Always access by column name**, never by integer index.

```python
# CRASHES: KeyError: 0
row[0]
# CORRECT
row["file_path"]
```

### 2. SEM Records Always Empty Bug (FIXED)

Root cause: `sample[0]` crash inside `fetch_full_report_data` at line 211.  
The crash prevented `data["sem_records"]` from being populated, so all SEM images were missing from reports.

Fix applied: `sample[0]` → `sample["file_path"]`

### 3. IMAGE_SIZE_CONFIG Key Derivation

For placeholder `{sem_records.image_2_B1-1}`:
- `clean_key` = `"image_2_B1-1"`
- Size key = `clean_key.upper().split("_")[0]` = `"IMAGE"`
- This lookup hits `IMAGE_SIZE_CONFIG["IMAGE"]` = `(1.50, 2.00, 0.02)`

### 4. _find_image_path Column Detection

The function scans `clean_key` for known column names. The col list must include `"file_path"` and `"image"`:
```python
for c in ["magnification", "accel_volt", "unit_id", "point_id", "file_path", "image"]:
```
Without `"image"`, placeholder `{sem_records.image_*}` resolves to `None` → image not inserted.

### 5. SEM Folder Detection in auto_pipeline.py

SEM source folders are detected as:
```python
f_upper.startswith('R') or f_upper == "CROSS SECTION INSPECTION"
```
Any folder starting with `'R'` or exactly named `"CROSS SECTION INSPECTION"` triggers SEM extraction.

### 6. Windows Console Encoding

Windows `cp1252` console cannot print Unicode arrows (`→`).  
Use `->` in print statements or set `PYTHONIOENCODING=utf-8`.

### 7. DB Password Not in Environment

Running backend without `DB_PASSWORD` set causes:
```
psycopg2.OperationalError: no password supplied
```
Set before starting:
```powershell
$env:DB_PASSWORD = "admin@postgres@2022"
$env:DB_HOST = "10.151.28.2"
$env:DB_NAME = "DPA"
$env:DB_USER = "postgres"
```

### 8. U3 Filtered from Preview

Frontend `CreateReport.jsx` filters out `U3` from Cross Section Inspection preview:
```javascript
.filter(u => u.toUpperCase() !== 'U3')
```
This is intentional — U3 is excluded from the preview display (but still stored in DB and may appear in the final report).

---

## 10. Feature Updates & Enhancements (May 2026)

### 10.1 Flexible DPA Report Detection
To prevent system breakage if the "4.DPA report" category is renamed (e.g., to "5.DPA report"), the backend now uses case-insensitive partial matching:
```sql
-- In product_request_service.py
WHERE UPPER(rt.rel_name) LIKE '%%DPA REPORT%%'
```
This ensures timepoints are discovered regardless of numbering or prefix changes.

### 10.2 X-RAY Naming Correction (1-1 -> 1)
For the X-RAY category, users occasionally mislabel files as `1-1_Xray.jpg` instead of `1_Xray.jpg`. The pipeline now includes specific logic for X-RAY to normalize these to `image_seq = '1'`:
```python
# In auto_pipeline.py
elif "X-RAY" in category.upper():
    seq_match = re.split(r'[_ -]', f)
    seq = seq_match[0] if seq_match else f.split("_")[0]
```
This forces the image into the first column (Image 1) in the report and preview.

### 10.3 DB-Driven Image Grouping
The frontend now prioritizes the `imageSeq` returned from the database over manual filename parsing. This ensures that any normalization done by the pipeline (like the X-RAY fix) is accurately reflected in the UI.

### 10.4 Placeholder & Missing Image Cleanup
To ensure professional-looking reports, the `DPAReportGenerator` now clears leftover tags:
- **Missing Data**: If a text placeholder (e.g., `{background_info.custom_field}`) is not found, it is replaced with an empty string.
- **Missing Images**: If an image file is missing, the placeholder text in the PowerPoint shape is cleared (`shape.text = ""`), leaving a blank space instead of a raw tag.

### 10.5 Custom Category Sorting
The "Select Sections to Include" list now follows a fixed logical order defined in the backend, rather than simple alphabetical sorting:
1. External Visual -> 2. Delam -> 3. X-Ray -> 4. Decap -> 5. IMC -> 6. C-R -> 7. BS,WP,SP -> 8. Cross Section.

### 10.6 UI Enhancements
- **Step 2 Summary Bar**: A subtle header was added to the "Verify" step showing the currently selected `PR`, `LOT`, and `DPA REPORT` name for better user context.
- **Unit ID Normalization**: Unit labels in the preview table were changed from `U1, U2...` to just `1, 2...` for a cleaner look.

### 10.7 Excel Filename Extension Stripping
The PowerPoint placeholder `{requests.excel_file_name}` maps to the original Excel source file (e.g., `PR-2026-001.xlsx`). To prevent the raw file extension (like `.xlsx`, `.xls`, `.xlsm`) from displaying in the generated slide report, `DPAReportGenerator` now automatically strips these extensions before rendering:
```python
# In report_generator.py
if "excel_file_name" in p_clean:
    val = meta.get("excel_file_name", "")
    if val and isinstance(val, str):
        for ext in [".xlsx", ".xlsm", ".xls"]:
            if val.lower().endswith(ext):
                val = val[:-len(ext)]
                break
```
This guarantees clean presentation of the original PR file name on the slides.

---

## 11. AI Inspection Pipeline (May 2026 Update)

In May 2026, the inspection pipeline for C-R (Cross-Section) and IMC (Intermetallic Compound) was upgraded to a high-precision AI-driven system.

### 11.1 High-Precision AI Segmentation (C-R)
The **C-R (Cross-Section)** category now uses a **Zoom-then-YOLO** strategy to solve the "peripheral noise" and "distorted crop" issues:
1. **Stage 1 (Scan):** Uses **FastSAM-s** to segment all potential objects in the full-scale image.
2. **Stage 2 (Zoom):** Selects the best candidate (using Surgical Scoring) and performs a focused crop (zoom) around it with a 30% margin.
3. **Stage 3 (Refine):** Re-runs a custom **YOLOv8** model on the zoomed image to get a pixel-perfect, surgical bounding box.

### 11.2 Clean-Image Priority Logic (IMC)
The **IMC** category handles measurement-labeled images (e.g., `1-1=94.10%.jpg`) and clean images (`1-1.jpg`) with a "Data-Image Separation" rule:
- **Data Source:** Percentage values are parsed from the filename of labeled images.
- **Image Source:** The system prioritizes the **clean image** (unlabeled) for the final crop to ensure professional-looking reports without text overlays. Labeled images are used as a fallback only if no clean image exists.
- **Key Normalization:** Multi-hyphen names (e.g., `1-1-1`) are normalized to standard keys (e.g., `1-1`) for accurate mapping.

### 11.3 Surgical Selection Scoring
To ensure the AI picks the "perfect" component instead of debris, a **Surgical Scoring** algorithm was implemented:
```python
score = (area * solidity^2) / (dist^0.2)
# Penalties applied for:
# - Objects touching image edges (90% reduction)
# - Extreme aspect ratios / skinny shapes (80% reduction)
```
This formula prioritizes large, complete (high solidity), and non-peripheral components.

### 11.4 U3 Filtering
To keep reports focused on primary inspection data, a **U3 Filter** was added to the C-R pipeline. Any files starting with "U3" (typically auxiliary data) are automatically ignored during the extraction process.

---

*End of Codewiki — D:\DPA System*
