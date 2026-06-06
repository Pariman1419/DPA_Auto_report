"""
API tests for /api/* product request endpoints.
Uses FastAPI TestClient and mocks out product_request_service / report_generator calls.
"""
import os
import pathlib
import pytest
from unittest.mock import MagicMock, patch
from models.schemas import ProductRequestData, BackgroundInfo, BillOfMaterial
from services.report_generator import OUTPUT_DIR

pytestmark = pytest.mark.api


# ── Dashboard & History ────────────────────────────────────────────────────────

def test_get_dashboard_stats(client, auth_cookies):
    """Stats endpoint returns summary counts from the service."""
    mock_stats = {"total_pr": 10, "total_generated": 25, "active_users": 5}
    with patch("routers.product_request.get_generation_stats", return_value=mock_stats):
        response = client.get("/api/stats", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.json() == mock_stats


def test_get_history(client, auth_cookies, sample_history):
    """History endpoint returns a list of past report generation records."""
    mock_history = [dict(sample_history)]
    with patch("routers.product_request.list_generation_history", return_value=mock_history):
        response = client.get("/api/history", cookies=auth_cookies)
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["pr_no"] == "PR2024001"


def test_download_history_file_success(client, auth_cookies, sample_history, tmp_path):
    """Successfully download a history record's PPTX if it exists on disk."""
    dummy_file = tmp_path / "test_report.pptx"
    dummy_file.write_bytes(b"dummy pptx data")

    record = dict(sample_history)
    record["file_path"] = str(dummy_file)

    with patch("routers.product_request.get_history_record", return_value=record):
        response = client.get("/api/history/1/download", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.content == b"dummy pptx data"
        assert "application/vnd.openxmlformats-officedocument.presentationml.presentation" in response.headers["content-type"]


def test_download_history_file_not_found_db(client, auth_cookies):
    """Attempting to download a non-existent history record returns 404."""
    with patch("routers.product_request.get_history_record", return_value=None):
        response = client.get("/api/history/999/download", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"


def test_download_history_file_not_found_disk(client, auth_cookies, sample_history):
    """Attempting to download a history record whose file is missing on disk returns 404."""
    record = dict(sample_history)
    record["file_path"] = "/nonexistent/file.pptx"

    with patch("routers.product_request.get_history_record", return_value=record):
        response = client.get("/api/history/1/download", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "File not found on disk"


def test_delete_history_success(client, auth_cookies):
    """Delete endpoint returns status: deleted when deletion succeeds."""
    with patch("routers.product_request.delete_history_record", return_value=True):
        response = client.delete("/api/history/1", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.json() == {"status": "deleted"}


def test_delete_history_not_found(client, auth_cookies):
    """Delete endpoint returns 404 if history record does not exist."""
    with patch("routers.product_request.delete_history_record", return_value=False):
        response = client.delete("/api/history/999", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "Record not found"


# ── Product Requests metadata ──────────────────────────────────────────────────

def test_get_all_product_requests(client, auth_cookies):
    """List endpoint returns all registered PRs."""
    mock_list = [{"productRequestNo": "PR2024001"}, {"productRequestNo": "PR2024002"}]
    with patch("routers.product_request.list_product_requests", return_value=mock_list):
        response = client.get("/api/product-requests", cookies=auth_cookies)
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2
        assert data[0]["productRequestNo"] == "PR2024001"
        assert data[1]["productRequestNo"] == "PR2024002"


def test_get_product_request_success(client, auth_cookies, sample_pr):
    """PR detail endpoint returns complete ProductRequestData model on success."""
    pr_data = ProductRequestData(
        productRequestNo="PR2024001",
        folderName="PR2024001",
        subject=sample_pr["subject"],
        purpose=sample_pr["purpose"],
        date=str(sample_pr["request_date"]),
        conclusion=sample_pr["conclusion"],
        backgroundInfo=BackgroundInfo(
            customerName=sample_pr["customer_name"],
            assemblySite=sample_pr["assembly_site"],
            packageType=sample_pr["package_type"],
            dateCode=sample_pr["date_code"],
            packageSize=sample_pr["package_size"],
            numberOfLot=str(sample_pr["number_of_lot"]),
            pinBallCount=str(sample_pr["pin_ball_count"]),
            requestorNameDept=sample_pr["requestor_name_dept"],
            reliabilityStaffName=sample_pr["reliability_staff_name"],
        ),
        billOfMaterial=BillOfMaterial(
            orderLot=sample_pr["order_lot"],
            custAssy=sample_pr["cust_assy"],
            device=sample_pr["device"],
            dieSize=sample_pr["die_size"],
            dapSize=sample_pr["dap_size"],
            lfStockNo=sample_pr["lf_stock_no"],
            dieAttachMaterial=sample_pr["die_attach_material"],
            wireType=sample_pr["wire_type"],
            moldCompound=sample_pr["mold_compound"],
            platingFinish=sample_pr["plating_finish"],
        ),
        reliabilityTests=[],
    )

    with patch("routers.product_request.read_product_request", return_value=pr_data):
        response = client.get("/api/product-request/PR2024001", cookies=auth_cookies)
        assert response.status_code == 200
        data = response.json()
        assert data["productRequestNo"] == "PR2024001"
        assert data["backgroundInfo"]["customerName"] == "MT0"
        assert data["billOfMaterial"]["orderLot"] == "MTDQS0906.1"


def test_get_product_request_not_found(client, auth_cookies):
    """PR detail endpoint returns 404 if PR number is missing from DB."""
    with patch("routers.product_request.read_product_request", side_effect=FileNotFoundError("PR not found")):
        response = client.get("/api/product-request/PR999999", cookies=auth_cookies)
        assert response.status_code == 404
        assert response.json()["detail"] == "PR not found"


# ── File Serving (Security Guards) ────────────────────────────────────────────

def test_download_report_success(client, auth_cookies):
    """download-report serves the file if it resides within safe folders."""
    dummy_report = pathlib.Path(OUTPUT_DIR) / "DPA_Report_test.pptx"
    dummy_report.write_bytes(b"report data")

    try:
        response = client.get(f"/api/download-report?path={dummy_report}", cookies=auth_cookies)
        assert response.status_code == 200
        assert response.content == b"report data"
    finally:
        if dummy_report.exists():
            dummy_report.unlink()


def test_download_report_path_traversal_denied(client, auth_cookies, tmp_path, monkeypatch):
    """download-report returns 403 if path escapes the output and image root directories."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("IMAGE_MOUNT_ROOT", str(tmp_path / "images"))
    
    # Target outside allowed roots
    forbidden_file = tmp_path / "confidential.txt"
    forbidden_file.write_bytes(b"secret")

    response = client.get(f"/api/download-report?path={forbidden_file}", cookies=auth_cookies)
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


def test_get_image_success(client, auth_cookies, tmp_path, monkeypatch):
    """get-image serves the image if it resides in the image mount root."""
    img_dir = tmp_path / "images"
    img_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("IMAGE_MOUNT_ROOT", str(img_dir))
    monkeypatch.setenv("IMAGE_WIN_ROOT", r"D:\Auto_detect\Result")

    dummy_img = img_dir / "sample.jpg"
    dummy_img.write_bytes(b"jpeg bytes")

    # Pass in DB path format (which starts with WIN_ROOT)
    db_path = r"D:\Auto_detect\Result\sample.jpg"
    response = client.get(f"/api/image?path={db_path}", cookies=auth_cookies)

    assert response.status_code == 200
    assert response.content == b"jpeg bytes"
    assert response.headers["content-type"] == "image/jpeg"


def test_get_image_path_traversal_denied(client, auth_cookies, tmp_path, monkeypatch):
    """get-image blocks arbitrary path lookups and returns 403."""
    img_dir = tmp_path / "images"
    img_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("IMAGE_MOUNT_ROOT", str(img_dir))

    # Dotdot attempt
    bad_path = r"D:\Auto_detect\Result\..\..\..\windows\system32\cmd.exe"
    response = client.get(f"/api/image?path={bad_path}", cookies=auth_cookies)
    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


# ── Report Generation ─────────────────────────────────────────────────────────

def test_generate_report_success(client, auth_cookies, tmp_path):
    """POST /api/generate-report correctly generates report and records in history."""
    gen_payload = {
        "prNumber": "PR2024001",
        "lot": "MTDQS0906.1",
        "timepoint": "T0",
        "userId": "EMP001",
        "selectedSections": {"EXTERNAL": True, "XRAY": True}  # Structured as dict[str, bool]
    }

    mock_stats = {"metadata_found": True, "images_found": 2, "images_missing": 0}
    mock_out = str(tmp_path / "output_report.pptx")

    # Build dummy outputs
    pathlib.Path(mock_out).touch()

    with patch("routers.product_request.get_next_revision", return_value="A"), \
         patch("routers.product_request.DPAReportGenerator") as mock_gen_cls, \
         patch("routers.product_request.save_generation_history") as mock_save_history:
        
        # Configure mock generator instance
        mock_gen_inst = MagicMock()
        mock_gen_inst.generate.return_value = (mock_out, mock_stats)
        mock_gen_cls.return_value = mock_gen_inst

        response = client.post("/api/generate-report", json=gen_payload, cookies=auth_cookies)

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["revision"] == "A"
        assert data["outputPath"] == mock_out
        assert data["filename"] == "output_report.pptx"
        
        # Verify generator instantiation
        mock_gen_cls.assert_called_once_with("PR2024001", "T0", "MTDQS0906.1", {"EXTERNAL": True, "XRAY": True}, revision="A")
        # Verify database history logging
        mock_save_history.assert_called_once_with(
            pr_no="PR2024001",
            lot="MTDQS0906.1",
            revision="A",
            timepoint="T0",
            user_id="EMP001",
            file_name="output_report.pptx",
            file_path=mock_out
        )
