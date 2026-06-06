# Database Design Input — DPA QA Report System

## Connection Details

| Parameter | Value |
|---|---|
| Engine | PostgreSQL 14+ |
| Host | 10.151.28.2 |
| Port | 5432 |
| Database | DPA |
| User | postgres (env: DB_USER) |
| Connection Pool | ThreadedConnectionPool min=1, max=10 |
| Oracle DW (PROMIS) | 10.151.25.145:1521/BSM (user: BSMUSER4) |

## Tables (12)

### users
บัญชีผู้ใช้งานระบบ

| Column | Type | Notes |
|---|---|---|
| user_id | VARCHAR PK | Employee ID |
| full_name | VARCHAR | ชื่อ-นามสกุล |
| email | VARCHAR | อีเมล (optional) |
| role | VARCHAR | `admin`, `QA Engineer`, `user` |
| password_hash | TEXT | bcrypt hash (upgrade จาก plaintext อัตโนมัติครั้งแรก login) |
| is_active | BOOLEAN | False จนกว่า Admin จะ approve |

### requests
หัวข้อ Product Request

| Column | Type | Notes |
|---|---|---|
| pr_no | VARCHAR PK | เช่น `PR2024001` |
| excel_file_name | VARCHAR | ชื่อไฟล์ Excel ต้นทาง (legacy) |

### info_requirements
ข้อมูล Subject / Purpose / Conclusion ของ PR

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| request_date | DATE | |
| subject | TEXT | |
| purpose | TEXT | |
| conclusion | TEXT | |

### background_info
ข้อมูล Background ของ PR (Customer, Package)

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| customer_name | VARCHAR | |
| assembly_site | VARCHAR | |
| package_type | VARCHAR | |
| date_code | VARCHAR | |
| package_size | VARCHAR | |
| number_of_lot | VARCHAR | |
| pin_ball_count | VARCHAR | |
| requestor_name_dept | VARCHAR | |
| reliability_staff_name | VARCHAR | |
| rel_request_number | JSONB | `{"1": "...", "2": "...", "3": "..."}` |

### bill_of_materials
BOM ต่อ Lot ของ PR (1 PR มีได้หลาย Lot)

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| order_lot | VARCHAR | Lot ID เช่น `MTDQS0906.1` |
| cust_assy | VARCHAR | |
| device | VARCHAR | |
| die_size | VARCHAR | |
| dap_size | VARCHAR | |
| lf_stock_no | VARCHAR | |
| die_attach_material | VARCHAR | |
| wire_type | VARCHAR | |
| mold_compound | VARCHAR | |
| plating_finish | VARCHAR | |

### reliability_tests
รายการ Reliability Test ของ PR

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| rel_name | VARCHAR | ชื่อ Test เช่น `HTSL`, `TC` |
| sample_size | VARCHAR | จำนวน Sample |
| lot_name | VARCHAR | Lot ที่ทำ Test |

### test_cases
ขั้นตอนย่อยของ Reliability Test

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| rel_test_id | INTEGER FK → reliability_tests | |
| name | VARCHAR | ชื่อ Step |
| result | VARCHAR | ผลการทดสอบ |
| status | VARCHAR | สถานะ |

### image_records
ที่เก็บ path ของภาพทุกใบ (Auto_detect เป็นผู้บันทึก)

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| timepoint | VARCHAR | `T0`, `- T0`, `T168`, ... |
| lot_name | VARCHAR | |
| category | VARCHAR | เช่น `1.EXTERNAL VISUAL`, `5.IMC` |
| image_seq | VARCHAR | Sequence เช่น `1-1`, `2-3` |
| image_name | VARCHAR | ชื่อไฟล์ |
| file_path | TEXT | Windows absolute path |

### imc_measurements
ค่า IMC % ของแต่ละ Unit

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| timepoint | VARCHAR | |
| lot_name | VARCHAR | |
| unit_id | VARCHAR | เช่น `1-1`, `3-5` (format: row-col) |
| imc_percent | NUMERIC | ค่า % เช่น `93.35` |

### sem_records
ข้อมูล SEM สำหรับ Cross Section Inspection

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| timepoint | VARCHAR | |
| lot_name | VARCHAR | |
| unit_id | VARCHAR | |
| point_id | VARCHAR | |
| magnification | VARCHAR | กำลังขยาย |
| accel_volt | VARCHAR | แรงดันไฟฟ้า |
| file_path | TEXT | path ของภาพ SEM |

### bond_measurements
ผล Bond Ability Test (Ball Shear / Wire Pull / Stitch Pull)

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR FK → requests | |
| timepoint | VARCHAR | |
| lot_name | VARCHAR | |
| test_type | VARCHAR | `Ball Shear`, `Wire Pull`, `Stitch Pull` |
| unit_id | VARCHAR | |
| force_value | NUMERIC | ค่าแรง (gram-force) |
| grade | VARCHAR | เกรด |
| failure_type | VARCHAR | ประเภทความล้มเหลว |

### report_generation_history
ประวัติการสร้างรายงาน

| Column | Type | Notes |
|---|---|---|
| id | SERIAL PK | |
| pr_no | VARCHAR | |
| order_lot | VARCHAR | |
| revision | VARCHAR | เช่น `A` |
| timepoint | VARCHAR | |
| user_id | VARCHAR | Employee ID ที่ Generate |
| file_name | VARCHAR | ชื่อไฟล์ PPTX |
| file_path | TEXT | absolute path ของไฟล์ |
| created_at | TIMESTAMP | เวลาที่ Generate |

## Oracle Datawarehouse (PROMIS)

ตาราง `PROMIS.BWIP_LOT` — ดึงข้อมูล Lot เพิ่มเติม

| Column | ใช้งาน |
|---|---|
| LOT | Lot ID (key) |
| CUST_CODE | รหัสลูกค้า |
| END_ENTITY_CODE | End Entity |
| DEVICE | ชื่อ Device |
| PACKAGE_CODE | รหัส Package |
| DATE_CODE | Date Code |
| CUST_ASSY_LOT | Customer Assembly Lot |

ข้อมูล DW จะ merge เข้า metadata ด้วย prefix `bwip.` ก่อนส่งให้ PPTX placeholder

## Indexes

| Table | Index | Columns | เหตุผล |
|---|---|---|---|
| image_records | idx_image_records_pr_tp_lot | (pr_no, timepoint, lot_name) | query หลักกรอง 3 ค่านี้ทุกครั้ง |
| image_records | idx_image_records_category | (category) | กรอง category ใน list_timepoint_folders |
| imc_measurements | idx_imc_measurements_pr_tp_lot | (pr_no, timepoint, lot_name) | preview + report generation |
| sem_records | idx_sem_records_pr_tp_lot | (pr_no, timepoint, lot_name) | preview + report generation |
| bond_measurements | idx_bond_measurements_pr_tp_lot | (pr_no, timepoint, lot_name) | preview + report generation |
| report_generation_history | idx_report_history_pr_no | (pr_no) | กรอง history ตาม PR |

## Timepoint Normalization

```sql
-- image_records.timepoint อาจมี prefix '- ' นำหน้า
-- ทุก query ใช้ pattern นี้
WHERE timepoint = %s OR LTRIM(timepoint, '- ') = %s
```
