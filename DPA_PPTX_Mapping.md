# DPA Report PPTX Mapping Documentation

เอกสารฉบับนี้ใช้สำหรับอ้างอิงในการ Mapping ข้อมูลจากฐานข้อมูล **DPA** เข้าสู่ Template PPTX โดยใช้ Placeholder ที่กำหนดไว้ใน `placeholder.json`

## 1. ข้อมูลพื้นฐานและประวัติ (Header & History)

| Placeholder | Database Table | Column / Logic | หมายเหตุ |
| :--- | :--- | :--- | :--- |
| `{requests.excel_file_name}` | `requests` | `excel_file_name` | ชื่อไฟล์ต้นฉบับ |
| `{report_generation_history.timepoint}` | `report_generation_history` | `timepoint` (User Input) | เช่น T0, HAST, TC (บันทึกตอนสั่ง Generate) |
| `{report_generation_history.revision}` | `report_generation_history` | `revision` | ตัวอักษร Rev ล่าสุดที่ระบบคำนวณให้ (A, B, C...) |

| `{info_requirements.request_date}` | `info_requirements` | `request_date` | Format: MMM DD'YY (เช่น Mar30'26) |
| `{values_records.IMC_1_1}` | `imc_measurements` | `imc_percent` where `unit_id` = '1-1' | ค่า IMC % (เช่น 94.1%) |
| `{values_records.IMC_1_2}` | `imc_measurements` | `imc_percent` where `unit_id` = '1-2' | ... จนถึง IMC_5_5 |


## 2. ข้อมูลสภาพแวดล้อม (Background Information)

| Placeholder | Database Table | Column / Logic |
| :--- | :--- | :--- |
| `{background_info.assembly_site}` | `background_info` | `assembly_site` |
| `{background_info.customer_name}` | `background_info` | `customer_name` |
| `{background_info.number_of_lot}` | `background_info` | `number_of_lot` |
| `{background_info.package_type}` | `background_info` | `package_type` |
| `{background_info.pin_ball_count}` | `background_info` | `pin_ball_count` |
| `{background_info.requestor_name_dept}` | `background_info` | `requestor_name_dept` |
| `{background_info.reliability_staff_name}` | `background_info` | `reliability_staff_name` |
| `{background_info.rel_request_number_1}` | `background_info` | `rel_request_number->>'1'` |
| `{background_info.rel_request_number_2}` | `background_info` | `rel_request_number->>'2'` |
| `{background_info.rel_request_number_3}` | `background_info` | `rel_request_number->>'3'` |
| `{background_info.date_code}` | `background_info` | `date_code` | |

## 3. ข้อมูลวัสดุ (Bill Of Materials)

| Placeholder | Database Table | Column / Logic |
| :--- | :--- | :--- |
| `{bill_of_materials.order_lot}` | `bill_of_materials` | `order_lot` |
| `{bill_of_materials.cust_assy}` | `bill_of_materials` | `cust_assy` |
| `{bill_of_materials.device}` | `bill_of_materials` | `device` |
| `{bill_of_materials.die_size}` | `bill_of_materials` | `die_size` |
| `{bill_of_materials.dap_size}` | `bill_of_materials` | `dap_size` |
| `{bill_of_materials.lf_stock_no}` | `bill_of_materials` | `lf_stock_no` |
| `{bill_of_materials.die_attach_material}` | `bill_of_materials` | `die_attach_material` |
| `{bill_of_materials.wire_type}` | `bill_of_materials` | `wire_type` |
| `{bill_of_materials.mold_compound}` | `bill_of_materials` | `mold_compound` |
| `{bill_of_materials.plating_finish}` | `bill_of_materials` | `plating_finish` |

## 4. ข้อมูลรูปภาพ (Image Records)

การดึงรูปภาพต้องใช้ `pr_no`, `timepoint` และเงื่อนไขเฉพาะของแต่ละหมวดหมู่ (Category) ในตาราง `image_records`

| Category | Placeholder Pattern | Filter: `category` | Filter: `image_seq` |
| :--- | :--- | :--- | :--- |
| **Visual** | `{Image_records. EXTERANAL_01}` | `1.EXTERNAL VISUAL` | `'1'`, `'2'`, ... |
| **Delam** | `{Image_records. DELAM_CSAM}` | `2.DELAM` | `'CSAM'` |
| **Delam** | `{Image_records. DELAM_TSAM}` | `2.DELAM` | `'TSAM'` |
| **X-Ray** | `{Image_records. XRAY_01}` | `3.X-RAY` | `'1'`, `'2'`, ... |
| **Decap** | `{Image_records.DECAP_1_1}` | `4.DECAP` | `'1-1'`, `'1-2'`, ... |
| **IMC** | `{Image_records. IMC_1_1}` | `5.IMC` | `'1-1'`, `'1-2'`, ... |
| **Cross Section** | `{Image_records.C-R_1_1}` | `6.C-R` | `'1-1'`, `'1-2'`, ... |

> [!NOTE]
> สำหรับ Placeholder ที่เป็นเลขรัน (เช่น `DECAP_01` ถึง `DECAP_25`) หากในฐานข้อมูลมีรูปไม่ครบ 25 รูป ให้เว้นว่างไว้ใน PPTX

## 5. ข้อมูลการวัด SEM (SEM Records)

หมวดหมู่นี้ใช้สำหรับดึงรายละเอียดการวัดจากตาราง `sem_records` (ส่วนใหญ่ใช้ในหน้า Cross Section)

| Placeholder Pattern | Column | Logic |
| :--- | :--- | :--- |
| `{sem_records.magnification_1_B1}` | `magnification` | ดึงค่าขยายของ Unit 1, Point B1 |
| `{sem_records.accel_volt_1_B1}` | `accel_volt` | ดึงค่า Voltage ของ Unit 1, Point B1 |
| `{sem_records.unit_id_1}` | `unit_id` | ดึงค่า Unit ID (กรณีใช้เป็น Label) |

## 6. ข้อมูลภายนอก (Data Warehouse)

| Placeholder | Source | สถานะ |
| :--- | :--- | :--- |
| `{BWIP.PACKAGE_CODE}` | Oracle PROMIS | `PROMIS.BWIP_LOT.PACKAGE_CODE` |

---
**เอกสารนี้อ้างอิงตามโครงสร้างฐานข้อมูลปัจจุบัน (Update: 2026-04-24)**

## 💡 ข้อแนะนำในการพัฒนา (Recommendations)

1.  **การจัดการรูปภาพที่หายไป**: 
    *   หาก Query แล้วไม่พบรูปภาพใน `image_records` (เช่น มีแค่ DECAP_1_1 ถึง 1-3 แต่ Slide ต้องการถึง 1-5) แนะนำให้ใช้ภาพ "Image Not Available" แทน หรือเว้นว่างไว้ เพื่อไม่ให้ระบบ Error
2.  **การดึงข้อมูล JSONB**:
    *   สำหรับ `rel_request_number` ให้ดึงโดยใช้ Operator `->>` ใน SQL เพื่อให้ได้ค่าเป็น String โดยตรง เช่น `SELECT rel_request_number->>'1' FROM background_info`
3.  **การจัดการ Revision และ Timepoint**:
    *   ระบบจะใช้ `get_next_revision` ในการหาตัวอักษร Revision ถัดไปอัตโนมัติ
    *   `timepoint` จะรับค่ามาจากหน้าจอ (Frontend) และบันทึกลงฐานข้อมูลพร้อมกับ Revision เพื่อใช้ในการ Mapping ลง Slide ต่อไป
4.  **ความถูกต้องของหน่วย (Units)**:
    *   ตรวจสอบข้อมูล `die_size`, `dap_size` ใน BOM ให้ดี เนื่องจากใน Excel อาจมีหน่วย (mils, mm) ติดมาด้วย ควรเก็บและแสดงผลให้ตรงตามต้นฉบับ
5.  **การตรวจสอบความสัมพันธ์ (Foreign Key)**:
    *   ข้อมูลในทุกตารางยึดโยงกันด้วย `pr_no` ดังนั้นเวลา Query ข้อมูลมาทำ Report แนะนำให้ใช้ `pr_no` เป็นเงื่อนไขหลักในทุกคำสั่ง SQL ครับ

