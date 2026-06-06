"""
Product Request Service
Handles fetching and managing Product Request data from the Database.
"""

import os
import pathlib
from typing import Optional

from fastapi.responses import FileResponse
from psycopg2.extras import RealDictCursor

from services.db_connector import DBConnector
from logger import get_logger
from models.schemas import (
    BackgroundInfo,
    BillOfMaterial,
    ReliabilityTest,
    TestStep,
    ProductRequestData,
)

_IMAGE_WIN_ROOT   = os.getenv("IMAGE_WIN_ROOT",   r"D:\Auto_detect\Result")
_IMAGE_MOUNT_ROOT = os.getenv("IMAGE_MOUNT_ROOT", _IMAGE_WIN_ROOT)


def _translate_image_path(path: str | None) -> str | None:
    """Translate a DB-stored Windows path to the actual path in this environment."""
    if not path:
        return path
    norm_path = path.replace("\\", "/")
    norm_win  = _IMAGE_WIN_ROOT.replace("\\", "/")
    if norm_path.lower().startswith(norm_win.lower()):
        relative = norm_path[len(norm_win):].lstrip("/")
        return str(pathlib.PurePosixPath(_IMAGE_MOUNT_ROOT) / relative)
    return path

DOC_ROOT = os.environ.get("DOC_ROOT", r"D:\DPA\doc")
log = get_logger("product_request_service")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _fetch_pr_metadata(cur, pr_no: str, lot: Optional[str] = None) -> dict | None:
    """
    Shared base query for PR metadata used by both read_product_request
    and fetch_full_report_data.  When lot is provided the BOM join is
    filtered to that lot; otherwise the first BOM row is returned.
    """
    params = []
    lot_join = ""
    if lot:
        lot_join = "AND bom.order_lot = %s"
        params.append(lot)
    params.append(pr_no)

    cur.execute(
        f"""
        SELECT
            r.pr_no, r.excel_file_name,
            i.request_date, i.subject, i.purpose, i.conclusion,
            b.customer_name, b.assembly_site, b.package_type,
            b.package_type AS package_code, b.date_code,
            b.package_size, b.number_of_lot, b.pin_ball_count,
            b.requestor_name_dept, b.reliability_staff_name,
            b.rel_request_number::jsonb->>'1' AS rel_request_number_1,
            b.rel_request_number::jsonb->>'2' AS rel_request_number_2,
            b.rel_request_number::jsonb->>'3' AS rel_request_number_3,
            bom.order_lot, bom.cust_assy, bom.device, bom.die_size,
            bom.dap_size, bom.lf_stock_no, bom.die_attach_material,
            bom.wire_type, bom.mold_compound, bom.plating_finish
        FROM requests r
        LEFT JOIN info_requirements i  ON r.pr_no = i.pr_no
        LEFT JOIN background_info b    ON r.pr_no = b.pr_no
        LEFT JOIN bill_of_materials bom ON r.pr_no = bom.pr_no {lot_join}
        WHERE r.pr_no = %s
        LIMIT 1
    """,
        params,
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------


def fetch_lot_from_dw(lot_id: str):
    """Fetch Lot details from Oracle Datawarehouse (PROMIS)."""
    log.info("[DW Service] Fetching Lot: %s from PROMIS...", lot_id)
    conn = DBConnector.get_dw_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT LOT, CUST_CODE, END_ENTITY_CODE, DEVICE,
                       PACKAGE_CODE, DATE_CODE, CUST_ASSY_LOT
                FROM PROMIS.BWIP_LOT
                WHERE LOT = :lot_id
            """,
                {"lot_id": lot_id},
            )
            row = cur.fetchone()
            if row:
                return {
                    "lot": row[0],
                    "custCode": row[1],
                    "endEntityCode": row[2],
                    "device": row[3],
                    "packageCode": row[4],
                    "dateCode": row[5],
                    "custAssyLot": row[6],
                }
            return None
    except Exception as e:
        log.error("Error fetching from DW: %s", e)
        return None
    finally:
        conn.close()


def fetch_full_report_data(pr_no: str, lot: str, timepoint: str) -> dict:
    """Fetch all data needed to generate a report."""
    log.info("fetch_full_report_data  PR=%s  lot=%s  timepoint=%s", pr_no, lot, timepoint)
    data = {"metadata": {}, "reliability_tests": [], "images": {}, "imc": []}

    conn = DBConnector.get_dpa_connection()
    if not conn:
        log.error("DB connection failed — returning empty data")
        return data

    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            meta = _fetch_pr_metadata(cur, pr_no, lot)
            if meta:
                data["metadata"] = meta
                log.debug("Metadata keys: %s", list(meta.keys()))
            else:
                log.warning("No metadata row found for PR=%s  lot=%s", pr_no, lot)

            # Fetch additional data from Oracle DW (PROMIS)
            if lot:
                dw_data = fetch_lot_from_dw(lot)
                if dw_data:
                    # Map DW fields to metadata with 'bwip.' prefix for PPTX placeholders
                    data["metadata"]["bwip.package_code"] = dw_data.get("packageCode")
                    data["metadata"]["bwip.cust_code"] = dw_data.get("custCode")
                    data["metadata"]["bwip.device"] = dw_data.get("device")
                    data["metadata"]["bwip.date_code"] = dw_data.get("dateCode")

            cur.execute(
                """
                SELECT rt.rel_name, rt.sample_size,
                       tc.name AS step_name, tc.result, tc.status
                FROM reliability_tests rt
                LEFT JOIN test_cases tc ON rt.id = tc.rel_test_id
                WHERE rt.pr_no = %s
                ORDER BY rt.id, tc.id
            """,
                (pr_no,),
            )
            data["reliability_tests"] = [dict(r) for r in cur.fetchall()]

            cur.execute(
                """
                SELECT category, image_seq, file_path
                FROM image_records
                WHERE pr_no = %s
                  AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s)
                  AND lot_name = %s
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            img_rows = cur.fetchall()
            for img in img_rows:
                key = f"{img['category']}_{img['image_seq']}".upper()
                data["images"][key] = img["file_path"]
            log.info("image_records fetched: %d rows  (TP=%s  lot=%s)", len(img_rows), timepoint, lot)

            cur.execute(
                """
                SELECT unit_id, imc_percent FROM imc_measurements
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            imc_rows = cur.fetchall()
            data["imc"] = [dict(r) for r in imc_rows]
            log.info("imc_measurements fetched: %d rows", len(imc_rows))

            # Fetch SEM Records (for Cross Section details like magnification, voltage) - Keep only Unit 1 and Unit 2
            cur.execute(
                """
                SELECT unit_id, point_id, magnification, accel_volt, file_path
                FROM sem_records
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                  AND (UPPER(unit_id) IN ('U1', 'U2') OR unit_id ILIKE '%%1' OR unit_id ILIKE '%%2')
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            sem_records = [dict(r) for r in cur.fetchall()]
            
            # Resolve full path for SEM images (they are stored in 'CROSS SECTION INSPECTION' folder)
            # Find the lot base folder first
            cur.execute(
                """
                SELECT file_path FROM image_records
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                LIMIT 1
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            sample = cur.fetchone()
            if sample and sem_records:
                # Translate path first to ensure proper OS separators inside container/host context
                sample_translated = _translate_image_path(sample["file_path"])
                # D:\...\images\T0\LOT\CATEGORY\FILE.jpg -> D:\...\images\T0\LOT
                lot_base = os.path.dirname(os.path.dirname(sample_translated))
                sem_base = os.path.join(lot_base, "CROSS SECTION INSPECTION")
                
                if not os.path.exists(sem_base):
                    # Fallback to category folder if CROSS SECTION INSPECTION doesn't exist
                    sem_base = os.path.join(lot_base, "6.C-R")

                for row in sem_records:
                    if row["file_path"]:
                        # Determine if path is absolute in a platform-agnostic way (handles both Windows and POSIX)
                        norm_fpath = row["file_path"].replace("\\", "/")
                        is_abs = norm_fpath.startswith("/") or (len(norm_fpath) > 1 and norm_fpath[1] == ":")
                        
                        if is_abs:
                            row["file_path"] = _translate_image_path(row["file_path"])
                        else:
                            row["file_path"] = _translate_image_path(os.path.join(sem_base, row["file_path"]))
            
            data["sem_records"] = sem_records
            log.info("sem_records fetched: %d rows", len(sem_records))

    except Exception as e:
        log.exception("Error in fetch_full_report_data: %s", e)
    finally:
        DBConnector.release_dpa_connection(conn)

    return data


def read_product_request(pr_no: str) -> ProductRequestData:
    """Fetch all details for a Product Request from the database."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        raise Exception("Database connection failed")
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            row = _fetch_pr_metadata(cur, pr_no)
            if not row:
                raise FileNotFoundError(
                    f"Product Request {pr_no} not found in database"
                )

            cur.execute(
                """
                SELECT id, rel_name, duration, test_condition, sample_size
                FROM reliability_tests
                WHERE pr_no = %s
            """,
                (pr_no,),
            )
            rel_rows = cur.fetchall()

            reliability_tests = []
            for rel in rel_rows:
                cur.execute(
                    """
                    SELECT name, duration, test_condition, sample_size, result, status
                    FROM test_cases
                    WHERE rel_test_id = %s
                """,
                    (rel["id"],),
                )
                steps = [TestStep(**s) for s in cur.fetchall()]
                reliability_tests.append(
                    ReliabilityTest(
                        name=rel["rel_name"],
                        duration=rel["duration"],
                        condition=rel["test_condition"],
                        sampleSize=rel["sample_size"],
                        status=None,
                        steps=steps,
                    )
                )

            return ProductRequestData(
                productRequestNo=row["pr_no"],
                folderName=row["pr_no"],
                subject=row["subject"] or "",
                purpose=row["purpose"] or "",
                date=str(row["request_date"] or ""),
                conclusion=row["conclusion"] or "",
                backgroundInfo=BackgroundInfo(
                    customerName=row["customer_name"] or "",
                    assemblySite=row["assembly_site"] or "",
                    packageType=row["package_type"] or "",
                    dateCode=row["date_code"] or "",
                    packageSize=row["package_size"] or "",
                    numberOfLot=str(row["number_of_lot"] or ""),
                    pinBallCount=str(row["pin_ball_count"] or ""),
                    requestorNameDept=row["requestor_name_dept"] or "",
                    reliabilityStaffName=row["reliability_staff_name"] or "",
                ),
                billOfMaterial=BillOfMaterial(
                    orderLot=row["order_lot"] or "",
                    custAssy=row["cust_assy"] or "",
                    device=row["device"] or "",
                    dieSize=row["die_size"] or "",
                    dapSize=row["dap_size"] or "",
                    lfStockNo=row["lf_stock_no"] or "",
                    dieAttachMaterial=row["die_attach_material"] or "",
                    wireType=row["wire_type"] or "",
                    moldCompound=row["mold_compound"] or "",
                    platingFinish=row["plating_finish"] or "",
                ),
                reliabilityTests=reliability_tests,
            )
    finally:
        DBConnector.release_dpa_connection(conn)


def list_product_requests() -> list[dict]:
    """Fetch the list of all available Product Requests from the database."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pr_no FROM requests ORDER BY pr_no DESC")
            return [{"productRequestNo": r[0]} for r in cur.fetchall()]
    finally:
        DBConnector.release_dpa_connection(conn)


def list_timepoints(pr_number: str, lot: Optional[str] = None) -> list[str]:
    """Fetch available timepoints for '4.DPA report', optionally filtered by lot."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            query = """
                SELECT DISTINCT tc.name
                FROM test_cases tc
                JOIN reliability_tests rt ON tc.rel_test_id = rt.id
                WHERE rt.pr_no = %s AND UPPER(rt.rel_name) LIKE '%%DPA REPORT%%'
            """
            params = [pr_number]
            if lot:
                query += " AND rt.lot_name = %s"
                params.append(lot)
            query += " ORDER BY tc.name"
            cur.execute(query, tuple(params))
            return [r[0].lstrip("- ").strip() for r in cur.fetchall() if r[0]]
    finally:
        DBConnector.release_dpa_connection(conn)


_IMC_SEQS = (
    "1-1","1-2","1-3","1-4","1-5",
    "2-1","2-2","2-3","2-4","2-5",
    "3-1","3-2","3-3","3-4","3-5",
    "4-1","4-2","4-3","4-4","4-5",
    "5-1","5-2","5-3","5-4","5-5",
)
_CR_SEQS = ("1-1","1-2","1-3","2-1","2-2","2-3")


def list_timepoint_folders(pr_number: str, timepoint: str, lot: str) -> list[dict]:
    """Fetch image categories and extra details for a specific lot from the database."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            tp = (pr_number, timepoint, timepoint, lot)

            # Query 1 — categories + IMC/CR valid counts in one pass
            imc_placeholders = ",".join(["%s"] * len(_IMC_SEQS))
            cr_placeholders  = ",".join(["%s"] * len(_CR_SEQS))
            cur.execute(
                f"""
                SELECT
                    category,
                    COUNT(*) AS file_count,
                    COUNT(*) FILTER (
                        WHERE UPPER(category) LIKE '%%IMC%%'
                          AND image_seq IN ({imc_placeholders})
                    ) AS imc_valid_count,
                    COUNT(*) FILTER (
                        WHERE (UPPER(category) LIKE '%%C-R%%' OR UPPER(category) LIKE '%%CR%%')
                          AND image_seq IN ({cr_placeholders})
                    ) AS cr_valid_count
                FROM image_records
                WHERE pr_no = %s
                  AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s)
                  AND lot_name = %s
                  AND UPPER(category) NOT LIKE '%%BOND ABILITY%%'
                GROUP BY category
                ORDER BY category
                """,
                list(_IMC_SEQS) + list(_CR_SEQS) + list(tp),
            )
            raw_rows = cur.fetchall()
            raw_folders = [{"name": r[0], "fileCount": r[1]} for r in raw_rows]
            imc_valid_file_count = next((r[2] for r in raw_rows if "IMC" in r[0].upper()), 0)
            cr_valid_file_count  = next(
                (r[3] for r in raw_rows if "C-R" in r[0].upper() or "CR" in r[0].upper()), 0
            )

            # Query 2 — IMC value count + bond type count + SEM count (combined)
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM imc_measurements
                     WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s) AS imc_count,
                    (SELECT COUNT(DISTINCT test_type) FROM bond_measurements
                     WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s) AS bond_count,
                    (SELECT COUNT(*) FROM sem_records
                     WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                       AND (UPPER(unit_id) IN ('U1', 'U2') OR unit_id ILIKE '%%1' OR unit_id ILIKE '%%2')) AS sem_count
                """,
                tp + tp + tp,
            )
            counts = cur.fetchone()
            imc_count, bond_count, sem_count = counts[0], counts[1], counts[2]

            bond_excel_path = find_bond_ability_excel(pr_number, timepoint, lot)
            has_bond_ability = bond_excel_path is not None

            folders = raw_folders

            # อัปเดตข้อมูลเข้าไปในลิสต์ของ Folder
            for f in folders:
                up_name = f["name"].upper()
                if "IMC" in up_name:
                    f["fileCount"] = imc_valid_file_count
                    f["imcCount"] = imc_count
                if "BS,WP,SP" in up_name:
                    f["hasBondAbility"] = has_bond_ability
                    f["bondCount"] = bond_count
                if ("CR" in up_name or "C-R" in up_name) and "CROSS" not in up_name:
                    f["fileCount"] = cr_valid_file_count
                if "CROSS SECTION" in up_name:
                    f["semCount"] = sem_count

            # ถ้ามีข้อมูล Bond (จาก DB หรือ Excel) แต่ไม่มีรูปภาพเลย ก็ควรแสดงให้เลือก
            if (has_bond_ability or bond_count > 0) and not any(
                "BS,WP,SP" in f["name"].upper() for f in folders
            ):
                folders.append(
                    {
                        "name": "7.BS,WP,SP",
                        "fileCount": 0,
                        "hasBondAbility": has_bond_ability,
                        "bondCount": bond_count,
                    }
                )

            # Define Custom Sort Order
            def get_category_priority(name: str) -> int:
                n = name.upper()
                if "EXTERNAL" in n: return 1
                if "DELAM" in n: return 2
                if "X-RAY" in n or "XRAY" in n: return 3
                if "DECAP" in n: return 4
                if "IMC" in n: return 5
                if "C-R" in n or "CR" in n: return 6
                if "BS,WP,SP" in n: return 7
                if "CROSS SECTION" in n: return 8
                return 99

            # Sort the final folder list
            folders.sort(key=lambda x: get_category_priority(x["name"]))

            return folders
    finally:
        DBConnector.release_dpa_connection(conn)


def list_preview_images(
    pr_no: str, timepoint: str, lot: str, category: str
) -> list[dict]:
    """Fetch image paths for a specific category to show as a preview."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            # ใช้ LIKE เพราะชื่อโฟลเดอร์ใน DB มีตัวเลขนำหน้า เช่น '1.EXTERNAL VISUAL'
            cur.execute(
                """
                SELECT file_path, image_seq
                FROM image_records 
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s AND category LIKE %s
                ORDER BY image_seq, image_name
            """,
                (pr_no, timepoint, timepoint, lot, f"%{category}%"),
            )
            return [
                {"fileName": r[0].replace("\\", "/").rsplit("/", 1)[-1], "filePath": r[0], "imageSeq": r[1]}
                for r in cur.fetchall()
            ]
    finally:
        DBConnector.release_dpa_connection(conn)


def list_preview_imc(pr_no: str, timepoint: str, lot: str) -> list[dict]:
    """Fetch IMC measurements to show as a preview."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT unit_id, imc_percent
                FROM imc_measurements 
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                ORDER BY id
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            return [{"unitId": r[0], "value": r[1]} for r in cur.fetchall()]
    finally:
        DBConnector.release_dpa_connection(conn)


def list_preview_sem(pr_no: str, timepoint: str, lot: str) -> list[dict]:
    """Fetch SEM records for Cross Section Inspection preview, grouped-ready by unit."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT unit_id, point_id, magnification, accel_volt, file_path
                FROM sem_records
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                  AND (UPPER(unit_id) IN ('U1', 'U2') OR unit_id ILIKE '%%1' OR unit_id ILIKE '%%2')
                ORDER BY unit_id, point_id
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            return [
                {
                    "unitId": r[0],
                    "pointId": r[1],
                    "magnification": r[2],
                    "accelVolt": r[3],
                    "filePath": r[4],
                    "fileName": r[4].replace("\\", "/").rsplit("/", 1)[-1] if r[4] else "",
                }
                for r in cur.fetchall()
            ]
    finally:
        DBConnector.release_dpa_connection(conn)


def list_preview_bond(pr_no: str, timepoint: str, lot: str) -> list[dict]:
    """Fetch Bond measurements to show as a preview."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT test_type, unit_id, force_value, grade, failure_type
                FROM bond_measurements 
                WHERE pr_no = %s AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s) AND lot_name = %s
                ORDER BY test_type, unit_id, id
            """,
                (pr_no, timepoint, timepoint, lot),
            )
            return [
                {
                    "testType": r[0],
                    "unitId": r[1],
                    "force": r[2],
                    "grade": r[3],
                    "type": r[4],
                }
                for r in cur.fetchall()
            ]
    finally:
        DBConnector.release_dpa_connection(conn)


def get_generation_stats() -> dict:
    """Retrieve summary statistics for the dashboard."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return {"total": 0, "generated": 0, "failed": 0}
    try:
        with conn.cursor() as cur:
            # เนื่องจากเราเก็บเฉพาะงานที่สำเร็จลง DB ในตอนนี้
            # จึงนับรวมเป็น 'generated' ทั้งหมด
            cur.execute("SELECT COUNT(*) FROM report_generation_history")
            total = cur.fetchone()[0]
            return {"total": total, "generated": total, "failed": 0}
    except Exception as e:
        log.error("Error fetching stats: %s", e)
        return {"total": 0, "generated": 0, "failed": 0}
    finally:
        DBConnector.release_dpa_connection(conn)


def list_lots(pr_no: str) -> list[str]:
    """List all unique lots that have images for a given PR."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT lot_name FROM image_records WHERE pr_no = %s ORDER BY lot_name",
                (pr_no,),
            )
            return [r[0] for r in cur.fetchall() if r[0]]
    finally:
        DBConnector.release_dpa_connection(conn)


def get_next_revision(pr_no: str, timepoint: str) -> str:
    """Always return 'A' as requested (no increment)."""
    return "A"


def save_generation_history(
    pr_no: str,
    lot: str,
    revision: str,
    timepoint: str,
    user_id: str,
    file_name: str,
    file_path: str,
) -> None:
    """Save the record of a generated report to the database."""
    log.info("[DB Service] Saving history for PR: %s by User: %s", pr_no, user_id)
    conn = DBConnector.get_dpa_connection()
    if not conn:
        log.error("Could not connect to database to save history.")
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO report_generation_history
                (pr_no, order_lot, revision, timepoint, user_id, file_name, file_path, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
            """,
                (pr_no, lot, revision, timepoint, user_id, file_name, file_path),
            )
        conn.commit()
        log.info("History saved successfully for PR: %s", pr_no)
    except Exception as e:
        log.error("Failed to save history: %s", e)
        conn.rollback()
    finally:
        DBConnector.release_dpa_connection(conn)


def get_history_record(record_id: int) -> dict | None:
    """Fetch a single history record by id."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return None
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM report_generation_history WHERE id = %s",
                (record_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    finally:
        DBConnector.release_dpa_connection(conn)


def delete_history_record(record_id: int, delete_file: bool = True) -> bool:
    """Delete a history record and optionally the file from disk."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return False
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT file_path FROM report_generation_history WHERE id = %s",
                (record_id,),
            )
            row = cur.fetchone()
            if not row:
                return False
            file_path = row["file_path"]
            cur.execute(
                "DELETE FROM report_generation_history WHERE id = %s", (record_id,)
            )
        conn.commit()
        if delete_file and file_path and os.path.exists(file_path):
            os.remove(file_path)
        return True
    except Exception as e:
        log.error("Error deleting history record %s: %s", record_id, e)
        conn.rollback()
        return False
    finally:
        DBConnector.release_dpa_connection(conn)


def list_generation_history(limit: int = 100) -> list[dict]:
    """Fetch report generation history ordered by newest first."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return []
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT h.id, h.pr_no, h.order_lot, h.revision, h.timepoint,
                       h.user_id, u.full_name AS user_name,
                       h.file_name, h.file_path, h.created_at
                FROM report_generation_history h
                LEFT JOIN users u ON h.user_id = u.user_id
                ORDER BY h.created_at DESC
                LIMIT %s
            """,
                (limit,),
            )
            return [
                {
                    "id": r["id"],
                    "prNo": r["pr_no"],
                    "lot": r["order_lot"],
                    "revision": r["revision"],
                    "timepoint": r["timepoint"],
                    "userId": r["user_id"],
                    "userName": r["user_name"] or r["user_id"],
                    "fileName": r["file_name"],
                    "filePath": r["file_path"],
                    "createdAt": (
                        r["created_at"].strftime("%Y-%m-%d %H:%M")
                        if r["created_at"]
                        else ""
                    ),
                    "excelPath": find_bond_ability_excel(
                        r["pr_no"], r["timepoint"], r["order_lot"]
                    ),
                }
                for r in cur.fetchall()
            ]
    finally:
        DBConnector.release_dpa_connection(conn)


def get_report_file(filepath: str):
    """Return the generated report file for download."""
    if os.path.exists(filepath):
        ext = os.path.splitext(filepath)[1].lower()
        media_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )
        if ext == ".xlsx":
            media_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        return FileResponse(
            path=filepath,
            filename=os.path.basename(filepath),
            media_type=media_type,
        )
    return None


def find_bond_ability_excel(pr_no: str, timepoint: str, lot: str):
    """Find BOND_ABILITY_REPORT.xlsx by looking up actual file_path from image_records."""
    conn = DBConnector.get_dpa_connection()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_path FROM image_records
                WHERE pr_no = %s
                  AND (timepoint = %s OR LTRIM(timepoint, '- ') = %s)
                  AND lot_name = %s
                LIMIT 1
                """,
                (pr_no, timepoint, timepoint, lot),
            )
            row = cur.fetchone()
            if not row or not row[0]:
                log.debug("find_bond_ability_excel: no image_records for PR=%s TP=%s lot=%s", pr_no, timepoint, lot)
                return None
            lot_base = os.path.dirname(os.path.dirname(_translate_image_path(row[0])))
            excel_path = os.path.join(lot_base, "7.BS,WP,SP", "BOND_ABILITY_REPORT.xlsx")
            if os.path.exists(excel_path):
                log.debug("Bond Excel found: %s", excel_path)
                return excel_path
            log.debug("Bond Excel not on disk: %s", excel_path)
            return None
    except Exception as e:
        log.warning("find_bond_ability_excel error: %s", e)
        return None
    finally:
        DBConnector.release_dpa_connection(conn)
