-- Test database seed — run against DPA_TEST database
-- psql -h localhost -U postgres -d DPA_TEST -f tests/seeds/seed_test_db.sql

-- Re-create schema (safe for test DB only)
\i schema.sql

-- ── Users ────────────────────────────────────────────────────────────────────
-- admin / admin1234
INSERT INTO users (user_id, full_name, email, role, password_hash, is_active)
VALUES ('admin', 'System Admin', 'admin@dpa.test', 'admin',
        '$2b$12$KIXjV3qJ8Z1mN2pL5oR7OuWvHkT9xYcBdEfGhAiJsPlQrMnUzSw4K', TRUE)
ON CONFLICT (user_id) DO NOTHING;

-- EMP001 / test1234  (QA Engineer, active)
INSERT INTO users (user_id, full_name, email, role, password_hash, is_active)
VALUES ('EMP001', 'QA Engineer One', 'qa@dpa.test', 'QA Engineer',
        '$2b$12$KIXjV3qJ8Z1mN2pL5oR7OuWvHkT9xYcBdEfGhAiJsPlQrMnUzSw4K', TRUE)
ON CONFLICT (user_id) DO NOTHING;

-- EMP999 — inactive (pending approval)
INSERT INTO users (user_id, full_name, email, role, password_hash, is_active)
VALUES ('EMP999', 'Pending User', 'pending@dpa.test', 'user',
        '$2b$12$KIXjV3qJ8Z1mN2pL5oR7OuWvHkT9xYcBdEfGhAiJsPlQrMnUzSw4K', FALSE)
ON CONFLICT (user_id) DO NOTHING;

-- ── PR2024001 ─────────────────────────────────────────────────────────────────
INSERT INTO requests (pr_no, excel_file_name)
VALUES ('PR2024001', 'PR2024001.xlsx')
ON CONFLICT (pr_no) DO NOTHING;

INSERT INTO info_requirements (pr_no, request_date, subject, purpose, conclusion)
VALUES ('PR2024001', '2024-01-15',
        'DPA Report for MT0 QFN32 Package',
        'Reliability evaluation at T0 timepoint for customer MT0',
        '')
ON CONFLICT DO NOTHING;

INSERT INTO background_info (
    pr_no, customer_name, assembly_site, package_type, date_code,
    package_size, number_of_lot, pin_ball_count,
    requestor_name_dept, reliability_staff_name, rel_request_number
) VALUES (
    'PR2024001', 'MT0', 'Hana Microelectronics', 'QFN', '2401',
    '5x5 mm', '1', '32',
    'QA Department', 'Reliability Staff A',
    '{"1": "REL-2024-001", "2": "", "3": ""}'
) ON CONFLICT DO NOTHING;

INSERT INTO bill_of_materials (
    pr_no, order_lot, cust_assy, device, die_size, dap_size,
    lf_stock_no, die_attach_material, wire_type, mold_compound, plating_finish
) VALUES (
    'PR2024001', 'MTDQS0906.1', 'MT0-QFN32-5x5', 'MT001',
    '3.0x3.0 mm', '3.1x3.1 mm',
    'LF-001', 'Ag Paste', 'Au 25um', 'EME-7351', 'NiPdAu'
) ON CONFLICT DO NOTHING;

INSERT INTO reliability_tests (pr_no, rel_name, sample_size, lot_name)
VALUES ('PR2024001', 'HTSL', '77', 'MTDQS0906.1')
ON CONFLICT DO NOTHING;

-- ── Image records (T0 / MTDQS0906.1) ─────────────────────────────────────────
INSERT INTO image_records (pr_no, timepoint, lot_name, category, image_seq, image_name, file_path)
VALUES
    ('PR2024001', 'T0', 'MTDQS0906.1', '1.EXTERNAL VISUAL', '1-1', '1-1.jpg',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\1.EXTERNAL VISUAL\1-1.jpg'),
    ('PR2024001', 'T0', 'MTDQS0906.1', '3.X-RAY', '1-1', '1-.jpg',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\3.X-RAY\1-.jpg'),
    ('PR2024001', 'T0', 'MTDQS0906.1', '4.DECAP', '1-1', '1.jpg',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\4.DECAP\1.jpg'),
    -- Timepoint with leading dash (normalization test)
    ('PR2024001', '- T0', 'MTDQS0906.1', '1.EXTERNAL VISUAL', '1-2', '1-2.jpg',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\1.EXTERNAL VISUAL\1-2.jpg')
ON CONFLICT DO NOTHING;

-- ── IMC measurements ──────────────────────────────────────────────────────────
INSERT INTO imc_measurements (pr_no, timepoint, lot_name, unit_id, imc_percent)
VALUES
    ('PR2024001', 'T0', 'MTDQS0906.1', '1-1', 93.35),
    ('PR2024001', 'T0', 'MTDQS0906.1', '1-2', 91.20),
    ('PR2024001', 'T0', 'MTDQS0906.1', '2-1', 94.10)
ON CONFLICT DO NOTHING;

-- ── SEM records ───────────────────────────────────────────────────────────────
INSERT INTO sem_records (pr_no, timepoint, lot_name, unit_id, point_id, magnification, accel_volt, file_path)
VALUES
    ('PR2024001', 'T0', 'MTDQS0906.1', '1', '1', '5000x', '15kV',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\CROSS SECTION\1-1.jpg'),
    ('PR2024001', 'T0', 'MTDQS0906.1', '1', '2', '5000x', '15kV',
     'D:\Auto_detect\Result\PR2024001\images\T0\MTDQS0906.1\CROSS SECTION\1-2.jpg')
ON CONFLICT DO NOTHING;

-- ── Bond measurements ─────────────────────────────────────────────────────────
INSERT INTO bond_measurements (pr_no, timepoint, lot_name, test_type, unit_id, force_value, grade, failure_type)
VALUES
    ('PR2024001', 'T0', 'MTDQS0906.1', 'Ball Shear', '1', 45.200, 'A', 'Normal'),
    ('PR2024001', 'T0', 'MTDQS0906.1', 'Wire Pull',  '1', 12.500, 'A', 'Normal')
ON CONFLICT DO NOTHING;

-- ── Generation history ────────────────────────────────────────────────────────
INSERT INTO report_generation_history
    (pr_no, order_lot, revision, timepoint, user_id, file_name, file_path)
VALUES
    ('PR2024001', 'MTDQS0906.1', 'A', 'T0', 'EMP001',
     'DPA_Report_PR2024001_T0_MTDQS0906.1_20240115_103045.pptx',
     '/tmp/dpa_test/DPA_Report_PR2024001_T0_MTDQS0906.1_20240115_103045.pptx')
ON CONFLICT DO NOTHING;
