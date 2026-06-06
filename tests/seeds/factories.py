"""
Test data factories for DPA.
Produce dict-based records that mirror psycopg2 RealDictCursor output.
"""
from __future__ import annotations
import random
import string
from datetime import datetime, date


def _rand_str(n=8) -> str:
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=n))


# ── User ──────────────────────────────────────────────────────────────────────
def make_user(
    user_id: str = None,
    full_name: str = "Test User",
    role: str = "QA Engineer",
    is_active: bool = True,
    password_hash: str = "$2b$12$KIXjV3qJ8Z1mN2pL5oR7OuWvHkT9xYcBdEfGhAiJsPlQrMnUzSw4K",
) -> dict:
    return {
        "user_id":       user_id or f"EMP{_rand_str(4)}",
        "full_name":     full_name,
        "email":         f"{(user_id or 'user').lower()}@dpa.test",
        "role":          role,
        "password_hash": password_hash,
        "is_active":     is_active,
        "created_at":    datetime.now(),
    }


# ── Product Request ───────────────────────────────────────────────────────────
def make_pr_row(
    pr_no: str = "PR2024001",
    customer: str = "MT0",
    lot: str = "MTDQS0906.1",
) -> dict:
    return {
        "pr_no":                   pr_no,
        "excel_file_name":         f"{pr_no}.xlsx",
        "request_date":            date(2024, 1, 15),
        "subject":                 f"DPA Report for {pr_no}",
        "purpose":                 "Reliability evaluation",
        "conclusion":              "",
        "customer_name":           customer,
        "assembly_site":           "Hana Microelectronics",
        "package_type":            "QFN",
        "package_code":            "QFN",
        "date_code":               "2401",
        "package_size":            "5x5 mm",
        "number_of_lot":           "1",
        "pin_ball_count":          "32",
        "requestor_name_dept":     "QA Department",
        "reliability_staff_name":  "Staff A",
        "rel_request_number_1":    "REL-2024-001",
        "rel_request_number_2":    "",
        "rel_request_number_3":    "",
        "order_lot":               lot,
        "cust_assy":               f"{customer}-QFN32",
        "device":                  "MT001",
        "die_size":                "3.0x3.0 mm",
        "dap_size":                "3.1x3.1 mm",
        "lf_stock_no":             "LF-001",
        "die_attach_material":     "Ag Paste",
        "wire_type":               "Au 25um",
        "mold_compound":           "EME-7351",
        "plating_finish":          "NiPdAu",
    }


# ── Image record ──────────────────────────────────────────────────────────────
def make_image_record(
    pr_no: str = "PR2024001",
    timepoint: str = "T0",
    lot: str = "MTDQS0906.1",
    category: str = "1.EXTERNAL VISUAL",
    seq: str = "1-1",
    win_path: str = None,
) -> dict:
    win_root = r"D:\Auto_detect\Result"
    path = win_path or f"{win_root}\\{pr_no}\\images\\{timepoint}\\{lot}\\{category}\\{seq}.jpg"
    return {
        "category":   category,
        "image_seq":  seq,
        "file_path":  path,
        "image_name": f"{seq}.jpg",
    }


# ── IMC measurement ───────────────────────────────────────────────────────────
def make_imc(unit_id: str = "1-1", value: float = 93.35) -> dict:
    return {"unit_id": unit_id, "imc_percent": value}


# ── SEM record ────────────────────────────────────────────────────────────────
def make_sem(unit_id: str = "1", point_id: str = "1",
             mag: str = "5000x", volt: str = "15kV",
             file_path: str = None) -> dict:
    fp = file_path or rf"D:\Auto_detect\Result\sem\{unit_id}-{point_id}.jpg"
    return {
        "unit_id":       unit_id,
        "point_id":      point_id,
        "magnification": mag,
        "accel_volt":    volt,
        "file_path":     fp,
    }


# ── Bond measurement ──────────────────────────────────────────────────────────
def make_bond(test_type: str = "Ball Shear", unit_id: str = "1",
              force: float = 45.2, grade: str = "A") -> dict:
    return {
        "test_type":    test_type,
        "unit_id":      unit_id,
        "force_value":  force,
        "grade":        grade,
        "failure_type": "Normal",
    }


# ── History record ────────────────────────────────────────────────────────────
def make_history(
    record_id: int = 1,
    pr_no: str = "PR2024001",
    lot: str = "MTDQS0906.1",
    timepoint: str = "T0",
    revision: str = "A",
    file_path: str = "/tmp/dpa/report.pptx",
) -> dict:
    return {
        "id":         record_id,
        "pr_no":      pr_no,
        "order_lot":  lot,
        "revision":   revision,
        "timepoint":  timepoint,
        "user_id":    "EMP001",
        "file_name":  f"DPA_Report_{pr_no}_{timepoint}_{lot}_20240115_103045.pptx",
        "file_path":  file_path,
        "created_at": "2024-01-15T10:30:45",
    }


# ── Full report data bundle (mirrors fetch_full_report_data output) ───────────
def make_full_report_data(
    pr_no: str = "PR2024001",
    lot: str = "MTDQS0906.1",
    timepoint: str = "T0",
) -> dict:
    return {
        "metadata": make_pr_row(pr_no=pr_no, lot=lot),
        "reliability_tests": [
            {"rel_name": "HTSL", "sample_size": "77",
             "step_name": "Initial", "result": "Pass", "status": "Done"}
        ],
        "images": {
            "EXTERNAL_1-1": rf"D:\Auto_detect\Result\{pr_no}\images\{timepoint}\{lot}\1.EXTERNAL VISUAL\1-1.jpg",
            "XRAY_1-1":     rf"D:\Auto_detect\Result\{pr_no}\images\{timepoint}\{lot}\3.X-RAY\1-1.jpg",
        },
        "imc": [make_imc("1-1"), make_imc("1-2", 91.20)],
        "sem_records": [make_sem("1", "1"), make_sem("1", "2")],
        "bond": [make_bond()],
    }
