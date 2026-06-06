# DPA Report SQL Queries Guide

รวบรวมคำสั่ง SQL สำหรับดึงข้อมูลมาใช้ในการ Generate PPTX Report

## 1. ข้อมูล Metadata หลัก (PR, Background, BOM)
ใช้สำหรับดึงข้อมูลพื้นฐานทั้งหมดมาใส่ใน Slide หน้าแรกๆ และตารางข้อมูลอุปกรณ์

```sql
SELECT 
    -- ข้อมูล PR
    r.pr_no, 
    r.excel_file_name, 
    r.pr_revision,
    
    -- ข้อมูลหัวข้อและความต้องการ
    i.request_date, 
    i.subject, 
    i.purpose,
    
    -- ข้อมูลสภาพแวดล้อม
    b.customer_name, 
    b.assembly_site, 
    b.package_type, 
    b.date_code, 
    b.package_size, 
    b.number_of_lot, 
    b.pin_ball_count, 
    b.requestor_name_dept, 
    b.reliability_staff_name,
    b.rel_request_number->>'1' as rel_req_1,
    b.rel_request_number->>'2' as rel_req_2,
    b.rel_request_number->>'3' as rel_req_3,
    
    -- ข้อมูลวัสดุ (BOM)
    bom.order_lot, 
    bom.cust_assy, 
    bom.device, 
    bom.die_size, 
    bom.dap_size, 
    bom.lf_stock_no, 
    bom.die_attach_material, 
    bom.wire_type, 
    bom.mold_compound, 
    bom.plating_finish

FROM requests r
LEFT JOIN info_requirements i ON r.pr_no = i.pr_no
LEFT JOIN background_info b ON r.pr_no = b.pr_no
LEFT JOIN bill_of_materials bom ON r.pr_no = bom.pr_no
WHERE r.pr_no = 'PR2024001' 
  AND bom.order_lot = 'LOT-A123'; -- ระบุเลข PR และ Lot ที่ต้องการ
```

## 2. ข้อมูลสรุปผลการทดสอบ (Reliability & Test Cases)
ใช้สำหรับดึงข้อมูลตาราง "Summary of DPA Result" ใน Slide หน้าสรุปผล

```sql
SELECT 
    rt.rel_name, 
    rt.duration, 
    rt.condition, 
    rt.sample_size,
    tc.name as step_name,
    tc.result,
    tc.status
FROM reliability_tests rt
LEFT JOIN test_cases tc ON rt.id = tc.rel_test_id
WHERE rt.pr_no = 'PR2024001'
ORDER BY rt.id, tc.id;
```

## 2. ข้อมูลรูปภาพ (Image Records)
ใช้สำหรับดึง Path ของรูปภาพทั้งหมดแยกตามประเภท

```sql
SELECT 
    category, 
    image_seq, 
    file_path 
FROM image_records 
WHERE pr_no = 'PR2024001' 
  AND timepoint = 'T0' -- ระบุ Timepoint (T0, HAST, TC, etc.)
ORDER BY category, image_seq;
```

## 3. ข้อมูลประวัติการออกรายงาน (History & Revision)
ใช้สำหรับเช็ค Revision ล่าสุดก่อนสร้างรายงานชุดใหม่

```sql
SELECT revision 
FROM report_generation_history 
WHERE pr_no = 'PR2024001' 
  AND timepoint = 'T0'
ORDER BY created_at DESC 
LIMIT 1;
```

## 4. ข้อมูลการวัด IMC (IMC Summary)
ใช้สำหรับดึงค่า % IMC ที่บันทึกไว้

```sql
SELECT 
    sample_id, 
    imc_percent 
FROM imc_measurements 
WHERE pr_no = 'PR2024001'
ORDER BY unit_id;
```

## 5. ข้อมูลจากระบบภายนอก (Oracle Data Warehouse)
ใช้ดึงข้อมูล Lot Detail จาก PROMIS โดยใช้ระบบ `DBConnector.get_dw_connection()`

```sql
-- รันบนระบบ Oracle (Data Warehouse)
SELECT 
    LOT, 
    CUST_CODE, 
    END_ENTITY_CODE, 
    DEVICE, 
    PACKAGE_CODE, 
    DATE_CODE, 
    CUST_ASSY_LOT 
FROM PROMIS.BWIP_LOT
WHERE LOT = 'MTDQS0906.1'; -- ระบุ Lot ID ที่ต้องการ
```

---
## 💡 เคล็ดลับในการเขียน Code (Backend Tips)

1.  **การดึงข้อมูลก้อนใหญ่ (Metadata)**: แนะนำให้ใช้ `dict_cursor` ใน Python เพื่อให้ได้ผลลัพธ์เป็น Dictionary ที่ชื่อ Key ตรงกับชื่อ Column จะทำให้ Mapping เข้า Placeholder ง่ายมาก
2.  **การจัดการรูปภาพ**: แนะนำให้ Query รูปภาพแยกตาม `category` แล้วเก็บเข้า Dictionary โดยใช้ `image_seq` เป็น Key เพื่อให้ตอนวนลูปใส่ Slide เรียกใช้ได้สะดวก
3.  **Handling Nulls**: ใน SQL แนะนำให้ใช้ `COALESCE(column, '')` หากต้องการให้ค่าที่เป็น NULL แสดงผลเป็นช่องว่างใน PPTX แทนคำว่า 'None'
