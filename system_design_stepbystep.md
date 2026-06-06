# System Design Step-by-Step — DPA QA Report System

## Architecture Overview

```
NAS: \\th1srnas6\FALab_DataSharing\...
  PR Folder / Timepoint / Lot / Category / images + Excel
          │
          │  [D:\Auto_detect — Preprocessing Pipeline]
          ▼
  watcher.py  ──poll 10 min──►  auto_pipeline.py
                                  ├── excel_reader.py  (PR metadata)
                                  ├── ext_visual.py    (EXTERNAL VISUAL)
                                  ├── ext_delam.py     (DELAM)
                                  ├── ext_xray.py      (X-RAY)
                                  ├── ext_decap.py     (DECAP)
                                  ├── ext_imc.py       (IMC — FastSAM AI)
                                  ├── ext_C_R.py       (C-R  — FastSAM AI)
                                  ├── ext_bonds.py     (BS,WP,SP)
                                  └── ext_sem.py       (CROSS SECTION)
                                         │
                          ┌──────────────┴──────────────┐
                          ▼                             ▼
              D:\Auto_detect\Result\          PostgreSQL (DPA)
              (processed images)              10.151.28.2:5432
                                                       │
          [D:\DPA — Web Application]                   │
                                                       │
┌─────────────────────────────────────────┐            │
│  Browser (React SPA — port 5190)        │            │
│  Vite proxy: /api/* → localhost:9090    │            │
└──────────────────┬──────────────────────┘            │
                   │ HTTP + httpOnly Cookie (JWT)       │
┌──────────────────▼──────────────────────┐            │
│  FastAPI Backend (port 9090)            │            │
│  ├── routers/auth.py                    │            │
│  └── routers/product_request.py         │            │
│       ├── product_request_service.py    ├────────────┤
│       ├── report_generator.py           │  psycopg2  │
│       ├── auth_service.py               │            │
│       └── db_connector.py              │◄───────────┘
└─────────────────────────────────────────┘
           │ oracledb
┌──────────▼──────────────────┐
│  Oracle PROMIS (DW)         │
│  10.151.25.145:1521/BSM     │
└─────────────────────────────┘
```

## Auto_detect Pipeline Detail (D:\Auto_detect)

### Entry Points
| ไฟล์ | หน้าที่ |
|---|---|
| `watcher.py` | Poll NAS ทุก `POLL_INTERVAL_MINUTES` (default 10 นาที), เรียก pipeline เฉพาะ PR ใหม่หรือที่มีการเปลี่ยนแปลง |
| `auto_pipeline.py` | Orchestrate extractor ทุกตัว, import DB, จัดการ RESULT_ROOT |

### Extractor Scripts (D:\Auto_detect\scripts\)
| Script | Category | วิธีการ |
|---|---|---|
| `ext_visual.py` | 1.EXTERNAL VISUAL | Copy/classify images |
| `ext_delam.py` | 2.DELAM | Copy/classify images |
| `ext_xray.py` | 3.X-RAY | Copy/classify images |
| `ext_decap.py` | 4.DECAP | Copy/classify images |
| `ext_imc.py` | 5.IMC | **FastSAM AI** crop Gold Ball + OCR ค่า % จาก filename |
| `ext_C_R.py` | 6.C-R | **FastSAM AI** segment Cross Section (รับมือขอบขาด) |
| `ext_bonds.py` | 7.BS,WP,SP | อ่าน BOND_ABILITY_REPORT Excel |
| `ext_sem.py` | CROSS SECTION | อ่าน `.txt` metadata (magnification, accel_volt) |

### Filename Filtering Rule (Strict Single-Dash)
```
ยอมรับ:  1-1.jpg          (unit-point)
         1-1=94.10%.jpg   (unit-point=value%)
ข้าม:    1-1-1.jpg        (multi-dash → ไม่ใช่ unit-point หลัก)
```

### Auto-Cleanup on Re-run
ทุกครั้งที่ process PR → **ล้างข้อมูลเก่าก่อนเสมอ** ป้องกันข้อมูลซ้ำซ้อน

### Path ที่ Auto_detect เขียนลง DB
```python
# image_records.file_path จะเก็บเป็น Windows path:
D:\Auto_detect\Result\{PR}\images\{Timepoint}\{Lot}\{Category}\file.jpg

# DPA backend แปลง path ผ่าน env vars:
IMAGE_WIN_ROOT   = D:\Auto_detect\Result
IMAGE_MOUNT_ROOT = (same หรือ path บน Linux mount)
```

## Step 1 — Request Lifecycle (Auth)

```
Client                   FastAPI                  PostgreSQL
  │── POST /api/auth/login ─►│                         │
  │   {userId, password}     │── SELECT users ────────►│
  │                          │◄── user row ────────────│
  │                          │  bcrypt.verify()        │
  │                          │  if plain-text → UPDATE hash
  │                          │  create_access_token()  │
  │◄── Set-Cookie: dpa_token ─│                         │
  │    + TokenResponse JSON  │                         │
```

- Token: HS256 JWT, payload: `{sub, name, role}`, TTL: `ACCESS_TOKEN_EXPIRE_HOURS`
- Cookie: `httpOnly=True`, `secure` จาก env `COOKIE_SECURE`, `samesite=lax`
- ทุก request หลังจากนี้ส่ง Cookie อัตโนมัติ (`credentials: 'include'` ใน fetch)

## Step 2 — User Registration Flow

```
Client → POST /api/auth/register {userId, fullName, password, email}
       → INSERT users SET is_active=False
       → send_approval_email(admin) พร้อม signed token (itsdangerous)
Admin → คลิก Link ใน email → GET /api/auth/approve/{token}
       → verify token (max_age=24h) → UPDATE users SET is_active=True
```

## Step 3 — Report Generation Flow

```
1. GET /api/product-requests          → รายการ PR ทั้งหมด
2. GET /api/product-request/{pr_no}   → ข้อมูล PR (metadata, BOM, tests)
3. GET /api/product-request/{pr_no}/lots           → รายการ Lot
4. GET /api/product-request/{pr_no}/timepoints?lot= → รายการ Timepoint
5. GET /api/product-request/{pr_no}/{tp}/folders?lot= → Categories + counts
6. GET /api/product-request/{pr_no}/{tp}/{lot}/preview-images?category=
   GET /api/product-request/{pr_no}/{tp}/{lot}/preview-imc
   GET /api/product-request/{pr_no}/{tp}/{lot}/preview-bond
   GET /api/product-request/{pr_no}/{tp}/{lot}/preview-sem
7. POST /api/generate-report {prNumber, timepoint, lot, selectedSections, userId}
   → DPAReportGenerator.generate()
   → save_generation_history()
   → return {outputPath, filename, stats}
8. GET /api/history/{id}/download → FileResponse (PPTX)
```

## Step 4 — PPTX Generation (DPAReportGenerator)

```python
load_data()
  ├── fetch_full_report_data(pr_no, lot, timepoint)
  │   ├── _fetch_pr_metadata()        → metadata dict
  │   ├── fetch_lot_from_dw()         → bwip.* fields (Oracle)
  │   ├── SELECT reliability_tests + test_cases
  │   ├── SELECT image_records        → images dict {CATEGORY_SEQ: file_path}
  │   ├── SELECT imc_measurements     → imc list
  │   └── SELECT sem_records          → sem_records list
  └── Presentation(TEMPLATE_PATH)

generate()
  ├── identify slides by placeholder pattern
  ├── delete unselected slides (_delete_slide)
  ├── _process_slide() per remaining slide
  │   ├── _replace_text_in_shape()    → _map_placeholder_to_value()
  │   ├── _replace_text_in_table()    → same mapper
  │   └── _insert_image_to_shape()    → PIL resize + pptx add_picture
  └── prs.save(OUTPUT_DIR/filename)
```

### Placeholder Mapping Rules

| Pattern | Source | ตัวอย่าง |
|---|---|---|
| `{background_info.field}` | metadata dict | `{background_info.customer_name}` |
| `{bill_of_materials.field}` | metadata dict | `{bill_of_materials.order_lot}` |
| `{bwip.field}` | Oracle DW | `{bwip.package_code}` |
| `{Image_records.CAT_SEQ}` | images dict | `{Image_records.EXTERNAL_1}` |
| `{values_records.IMC_R_C}` | imc list | `{values_records.IMC_1_1}` |
| `{sem_records.field_U_P}` | sem_records list | `{sem_records.magnification_1_1}` |

## Step 5 — Image Serving

```
GET /api/image?path=D:\Auto_detect\Result\...
  → _resolve_image_path(path)
      ├── replace IMAGE_WIN_ROOT prefix → IMAGE_MOUNT_ROOT
      └── return pathlib.Path
  → assert resolved.is_relative_to(IMAGE_MOUNT_ROOT)  ← path traversal guard
  → FileResponse(resolved)
```

## Step 6 — Path Security Pattern

ทุก endpoint ที่ serve ไฟล์ต้องทำ:
```python
safe_root = pathlib.Path(ALLOWED_ROOT).resolve()
requested = resolve_path(user_input).resolve()
if not requested.is_relative_to(safe_root):
    raise HTTPException(403)
```
ห้ามใช้ string comparison เพราะ `../` bypass ได้

## Step 7 — Auth Dependency Chain

```
get_current_user(request, credentials)
  ├── อ่าน cookie "dpa_token"  (primary)
  ├── อ่าน Bearer header       (fallback)
  └── decode_token() → JWTError → 401

require_role(*roles)(user=Depends(get_current_user))
  └── user["role"] not in roles → 403

require_admin = require_role("admin", "QA Engineer")
```

## Step 8 — Frontend State Machine

```
App
├── !user  → LoginPage / RegisterPage
└── user   →
    ├── page="create"    → CreateReport (3-step wizard)
    │   ├── Step 1: เลือก PR + Lot + Timepoint
    │   ├── Step 2: Preview ข้อมูล + เลือก Sections
    │   └── Step 3: Generate + Download
    ├── page="history"   → HistoryPage
    └── page="dashboard" → Stats cards
```

## Environment Variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| DB_HOST | ✅ | — | PostgreSQL host |
| DB_USER | ✅ | — | PostgreSQL user |
| DB_PASSWORD | ✅ | — | PostgreSQL password |
| JWT_SECRET_KEY | ✅ | — | JWT signing key |
| DB_NAME | | DPA | Database name |
| DB_PORT | | 5432 | PostgreSQL port |
| DOC_ROOT | | D:\DPA\doc | Excel files root |
| TEMPLATE_PATH | | D:\DPA\Template\DPA report.pptx | PPTX template |
| OUTPUT_DIR | | D:\DPA\output | Generated reports |
| IMAGE_WIN_ROOT | | D:\Auto_detect\Result | Path prefix in DB |
| IMAGE_MOUNT_ROOT | | same as WIN_ROOT | Local mount path |
| ALLOWED_ORIGINS | | http://localhost:3000 | CORS origins (comma-separated) |
| COOKIE_SECURE | | false | true ใน HTTPS production |
| SMTP_HOST | | — | Email server |
| SMTP_PORT | | 25 | Email port |
| APPROVER_EMAIL | | — | Admin email |
| SENDER_EMAIL | | — | Sender email |
| BASE_URL | | http://localhost:9090 | Base URL สำหรับ approval link |
| DW_USER | | — | Oracle DW user |
| DW_PASSWORD | | — | Oracle DW password |
| DW_DSN | | — | Oracle DSN |
| PORT | | 9090 | Backend port |
