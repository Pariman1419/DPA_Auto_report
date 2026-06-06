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

### POST /api/auth/register **[public]**
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

### GET /api/auth/approve/{token} **[admin, QA Engineer only]**
```
// token — signed itsdangerous token (24h expiry) from approval email

// Response 200
{ "message": "User EMP002 has been approved and activated." }

// Error 400 — expired or invalid token
// Error 404 — user not found
```

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

### POST /api/generate-report
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

## History

### GET /api/history
```json
// Response 200
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

// Error 404 — record not found or file missing on disk
```

### DELETE /api/history/{record_id}
```json
// Response 200
{ "status": "deleted" }

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

### GET /api/download-report?path={path}
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
{ "status": "ok" }
```

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
