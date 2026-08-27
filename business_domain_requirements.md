# Business Domain Requirements — DPA QA Report System

## 1. ภาพรวมธุรกิจ (Business Overview)

DPA (Destructive Physical Analysis) เป็นกระบวนการทดสอบความน่าเชื่อถือของ Semiconductor Package ที่ Hana Microelectronics ใช้งาน ระบบนี้สร้างขึ้นเพื่อแทนที่การจัดการข้อมูลด้วย Excel ไฟล์กระจายหลาย Machine ด้วยระบบกลางที่มี Database และสามารถ Generate รายงาน PowerPoint ได้อัตโนมัติ

## 2. ผู้ใช้งาน (Stakeholders)

| Role | หน้าที่ |
|---|---|
| QA Engineer | สร้าง Product Request (PR), เลือกข้อมูล Lot/Timepoint, Generate รายงาน |
| Admin | อนุมัติบัญชีผู้ใช้ใหม่, จัดการสิทธิ์ |
| Reliability Staff | กรอกข้อมูล BOM, Background Info, Reliability Tests |
| System (Auto_detect) | บันทึก Image paths และ Measurement values เข้า DB โดยอัตโนมัติ |

## 3. ขั้นตอนการทำงานหลัก (Core Workflow)

ระบบแบ่งเป็น 2 โปรเจคที่ทำงานร่วมกัน:

```
━━━━━━━━━━━━━━ PHASE 1: Auto_detect (Preprocessing) ━━━━━━━━━━━━━━

NAS (\\th1srnas6\FALab_DataSharing\...)
  └── PR Folder / Timepoint / Lot / Category /
          │
          ▼  watcher.py (poll ทุก 10 นาที)
          │
          ▼  auto_pipeline.py
     ┌────┴────────────────────────────────┐
     │ excel_reader  → requests, BOM, tests │
     │ ext_visual    → 1.EXTERNAL VISUAL    │
     │ ext_delam     → 2.DELAM              │
     │ ext_xray      → 3.X-RAY              │
     │ ext_decap     → 4.DECAP              │
     │ ext_imc       → 5.IMC (FastSAM AI)   │
     │ ext_C_R       → 6.C-R  (FastSAM AI)  │
     │ ext_bonds     → 7.BS,WP,SP           │
     │ ext_sem       → CROSS SECTION        │
     └────┬────────────────────────────────┘
          │
          ▼  D:\Auto_detect\Result\  (processed images)
          ▼  PostgreSQL DPA (image_records, measurements)

━━━━━━━━━━━━━━ PHASE 2: DPA Web App ━━━━━━━━━━━━━━

1. QA Engineer เข้าสู่ระบบ DPA Web App (port 5190)
2. เลือก Product Request (PR Number)
3. เลือก Lot และ Timepoint (T0, T168, T500, ...)
4. Preview ข้อมูลแต่ละ Category (ภาพ, IMC, Bond, SEM)
5. เลือก Sections ที่ต้องการรวมในรายงาน
6. กด Generate → ระบบสร้างไฟล์ PPTX จาก Template
7. Download รายงาน PPTX
```

## 4. Observability (Distributed Tracing)

ระบบ Backend มีการติดตั้ง OpenTelemetry สำหรับ distributed tracing โดย export ผ่าน OTLP ไปยัง collector ภายนอก (เช่น Jaeger)

- **ทำอะไร:** เก็บ trace ของทุก request ที่เข้ามาที่ FastAPI backend เพื่อดู latency และ error แต่ละ endpoint รวมถึง pipeline การ generate รายงาน
- **ทำไม:** เพิ่มความสามารถในการ debug และ monitor ประสิทธิภาพของระบบใน production ซึ่งไม่มี requirement เดิมครอบคลุมส่วนนี้ — เป็นการเพิ่มเติมที่ทีมยอมรับและบันทึกย้อนหลัง (เดิมถูกเพิ่มเข้ามาในโค้ดโดยไม่มีเอกสารรองรับ พบจาก code review วันที่ 2026-08-27)
- **Infra dependency ใหม่:** Backend คาดหวังว่า Docker network ชื่อ `observability-net` (external) จะมีอยู่แล้วในสภาพแวดล้อมที่ deploy (เช่น OTEL collector หรือ Jaeger stack) — เป็น precondition ก่อน deploy เดียวกับ `DB_HOST` ที่ต้องมี PostgreSQL พร้อมใช้งาน การเริ่มระบบจะไม่ fail หาก network นี้ไม่มี (wrapped in try/except ที่ `backend/main.py`), แต่ tracing จะไม่ทำงาน

## 5. Image Categories (หมวดหมู่ภาพ)

| ลำดับ | Category | คำอธิบาย |
|---|---|---|
| 1 | EXTERNAL VISUAL | ภาพถ่ายภายนอก Package |
| 2 | DELAM | Delamination Scan (Ultrasonic) |
| 3 | X-RAY | X-Ray Inspection |
| 4 | DECAP | ภาพหลัง Decapsulation |
| 5 | IMC | Intermetallic Compound (ค่า % + ภาพ) |
| 6 | C-R | Cross Section / SEM |
| 7 | BS,WP,SP | Bond Ability (Ball Shear, Wire Pull, Stitch Pull) |

## 6. โครงสร้าง Product Request (PR)

```
PR Number (เช่น PR2024001)
└── Background Info (Customer, Package Type, ...)
└── Info Requirements (Subject, Purpose, Conclusion)
└── Bill of Materials (1 BOM ต่อ 1 Lot)
    └── Timepoints (T0, T168, T500, ...)
        └── Image Records (ภาพแยกตาม Category)
        └── IMC Measurements (ค่า % ต่อ Unit)
        └── SEM Records (Cross Section)
        └── Bond Measurements (Ball Shear / Wire Pull / Stitch Pull)
```

## 7. Timepoint Naming

- Timepoints จาก DB อาจมี prefix `- ` นำหน้า เช่น `- T0` → ระบบ normalize ด้วย `LTRIM(timepoint, '- ')`
- รูปแบบที่พบ: `T0`, `T168`, `T500`, `T1000`

## 8. รายงาน PPTX

- ใช้ Template ที่กำหนด Placeholder ในรูปแบบ `{table.column}` เช่น `{background_info.customer_name}`
- Placeholder พิเศษ: `{Image_records.CATEGORY_SEQ}` → แทนที่ด้วย Image จริง
- Placeholder IMC: `{values_records.IMC_1_1}` → ค่า % ของ Unit 1-1
- Placeholder SEM: `{sem_records.magnification_UNIT_POINT}` → ค่า magnification
- Slides ที่ไม่ถูกเลือก Section จะถูกลบออกจาก PPTX ก่อน Generate

## 9. ข้อกำหนดความปลอดภัย

- ผู้ใช้ใหม่ต้องรอ Admin อนุมัติก่อน Login ได้
- JWT เก็บใน `httpOnly` Cookie (ป้องกัน XSS)
- ทุก endpoint ต้องผ่าน `get_current_user` dependency
- File serving endpoints ต้อง validate path อยู่ภายใน allowed root
- Rate limiting 5 req/min บน sensitive endpoints

## 10. Path Translation (Image Paths)

- Image paths ใน DB เก็บเป็น Windows path (เช่น `D:\Auto_detect\Result\...`)
- ระบบแปลง path ด้วย `IMAGE_WIN_ROOT` → `IMAGE_MOUNT_ROOT` เพื่อรองรับ cross-environment
- ตัวแปรใน `.env`: `IMAGE_WIN_ROOT`, `IMAGE_MOUNT_ROOT`
