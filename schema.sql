-- DPA QA Report System — PostgreSQL Schema
-- Database: DPA  |  Host: 10.151.28.2:5432
-- Run as: psql -h 10.151.28.2 -U postgres -d DPA -f schema.sql

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id       VARCHAR(50)  PRIMARY KEY,
    full_name     VARCHAR(200) NOT NULL,
    email         VARCHAR(200),
    role          VARCHAR(50)  NOT NULL DEFAULT 'user',
    password_hash TEXT         NOT NULL,
    is_active     BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- requests  (Product Request header)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS requests (
    pr_no           VARCHAR(50) PRIMARY KEY,
    excel_file_name VARCHAR(500),
    created_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- info_requirements  (Subject / Purpose / Conclusion)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS info_requirements (
    id           SERIAL      PRIMARY KEY,
    pr_no        VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    request_date DATE,
    subject      TEXT,
    purpose      TEXT,
    conclusion   TEXT
);

-- ---------------------------------------------------------------------------
-- background_info  (Customer / Package details)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS background_info (
    id                     SERIAL      PRIMARY KEY,
    pr_no                  VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    customer_name          VARCHAR(200),
    assembly_site          VARCHAR(200),
    package_type           VARCHAR(200),
    date_code              VARCHAR(50),
    package_size           VARCHAR(100),
    number_of_lot          VARCHAR(50),
    pin_ball_count         VARCHAR(50),
    requestor_name_dept    VARCHAR(200),
    reliability_staff_name VARCHAR(200),
    rel_request_number     JSONB        -- {"1": "...", "2": "...", "3": "..."}
);

-- ---------------------------------------------------------------------------
-- bill_of_materials  (BOM per Lot — 1 PR can have multiple Lots)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bill_of_materials (
    id                 SERIAL      PRIMARY KEY,
    pr_no              VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    order_lot          VARCHAR(100),   -- e.g. MTDQS0906.1
    cust_assy          VARCHAR(200),
    device             VARCHAR(200),
    die_size           VARCHAR(100),
    dap_size           VARCHAR(100),
    lf_stock_no        VARCHAR(100),
    die_attach_material VARCHAR(200),
    wire_type          VARCHAR(200),
    mold_compound      VARCHAR(200),
    plating_finish     VARCHAR(200)
);

-- ---------------------------------------------------------------------------
-- reliability_tests
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reliability_tests (
    id          SERIAL      PRIMARY KEY,
    pr_no       VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    rel_name    VARCHAR(200),   -- e.g. HTSL, TC, HAST
    sample_size VARCHAR(50),
    lot_name    VARCHAR(100)
);

-- ---------------------------------------------------------------------------
-- test_cases  (steps inside a reliability test)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS test_cases (
    id          SERIAL   PRIMARY KEY,
    rel_test_id INTEGER  NOT NULL REFERENCES reliability_tests(id) ON DELETE CASCADE,
    name        VARCHAR(200),
    result      VARCHAR(200),
    status      VARCHAR(100)
);

-- ---------------------------------------------------------------------------
-- image_records  (populated by Auto_detect pipeline)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS image_records (
    id          SERIAL      PRIMARY KEY,
    pr_no       VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    timepoint   VARCHAR(50),    -- e.g. T0, - T0, T168
    lot_name    VARCHAR(100),
    category    VARCHAR(200),   -- e.g. 1.EXTERNAL VISUAL, 5.IMC
    image_seq   VARCHAR(50),    -- e.g. 1-1, 2-3
    image_name  VARCHAR(500),
    file_path   TEXT            -- Windows absolute path stored by Auto_detect
);

CREATE INDEX IF NOT EXISTS idx_image_records_pr_tp_lot
    ON image_records(pr_no, timepoint, lot_name);

CREATE INDEX IF NOT EXISTS idx_image_records_category
    ON image_records(category);

-- ---------------------------------------------------------------------------
-- imc_measurements  (IMC % per unit, populated by Auto_detect)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS imc_measurements (
    id          SERIAL      PRIMARY KEY,
    pr_no       VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    timepoint   VARCHAR(50),
    lot_name    VARCHAR(100),
    unit_id     VARCHAR(20),    -- e.g. 1-1, 3-5  (row-col format)
    imc_percent NUMERIC(6, 2)   -- e.g. 93.35
);

CREATE INDEX IF NOT EXISTS idx_imc_measurements_pr_tp_lot
    ON imc_measurements(pr_no, timepoint, lot_name);

-- ---------------------------------------------------------------------------
-- sem_records  (Cross Section Inspection, populated by Auto_detect)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sem_records (
    id            SERIAL      PRIMARY KEY,
    pr_no         VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    timepoint     VARCHAR(50),
    lot_name      VARCHAR(100),
    unit_id       VARCHAR(20),
    point_id      VARCHAR(20),
    magnification VARCHAR(50),  -- e.g. 5000x
    accel_volt    VARCHAR(50),  -- e.g. 15kV
    file_path     TEXT
);

CREATE INDEX IF NOT EXISTS idx_sem_records_pr_tp_lot
    ON sem_records(pr_no, timepoint, lot_name);

-- ---------------------------------------------------------------------------
-- bond_measurements  (Ball Shear / Wire Pull / Stitch Pull)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS bond_measurements (
    id           SERIAL      PRIMARY KEY,
    pr_no        VARCHAR(50) NOT NULL REFERENCES requests(pr_no) ON DELETE CASCADE,
    timepoint    VARCHAR(50),
    lot_name     VARCHAR(100),
    test_type    VARCHAR(100),   -- Ball Shear | Wire Pull | Stitch Pull
    unit_id      VARCHAR(20),
    force_value  NUMERIC(8, 3),  -- gram-force
    grade        VARCHAR(20),
    failure_type VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_bond_measurements_pr_tp_lot
    ON bond_measurements(pr_no, timepoint, lot_name);

-- ---------------------------------------------------------------------------
-- report_generation_history
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS report_generation_history (
    id         SERIAL       PRIMARY KEY,
    pr_no      VARCHAR(50),
    order_lot  VARCHAR(100),
    revision   VARCHAR(10),
    timepoint  VARCHAR(50),
    user_id    VARCHAR(50),
    file_name  VARCHAR(500),
    file_path  TEXT,
    created_at TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_report_history_pr_no
    ON report_generation_history(pr_no);

-- ---------------------------------------------------------------------------
-- Seed Data (development / initial state)
-- ---------------------------------------------------------------------------

-- Admin user (password: admin1234  →  bcrypt hash below)
INSERT INTO users (user_id, full_name, email, role, password_hash, is_active)
VALUES ('admin', 'System Admin', 'admin@dpa.local', 'admin',
        '$2b$12$KIXjV3qJ8Z1mN2pL5oR7OuWvHkT9xYcBdEfGhAiJsPlQrMnUzSw4K', TRUE)
ON CONFLICT (user_id) DO NOTHING;

-- Sample PR: PR2024001
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

-- ---------------------------------------------------------------------------
-- Notes
-- ---------------------------------------------------------------------------
-- 1. Timepoint normalization: stored values may have leading "- " prefix.
--    All queries use: WHERE timepoint = %s OR LTRIM(timepoint, '- ') = %s
--
-- 2. image_records.file_path stores Windows paths (D:\Auto_detect\Result\...)
--    Backend translates via IMAGE_WIN_ROOT → IMAGE_MOUNT_ROOT env vars.
--
-- 3. users.password_hash may be plain-text for legacy accounts.
--    Backend upgrades to bcrypt on first successful login automatically.
--
-- 4. rel_request_number in background_info is JSONB: {"1":"val","2":"val","3":"val"}
--    Accessed in queries as: rel_request_number::jsonb->>'1'
