"""
Unit tests for services/report_generator.py

Focus areas:
  - IMAGE_SIZE_CONFIG correctness (including EXTERANAL typo key)
  - _translate_image_path
  - _identify_slide_category (C-R vs CROSS SECTION INSPECTION separation)
  - _map_placeholder_to_value (text replacement)
  - _get_image_dimensions cache
"""
import os
import sys
import pathlib
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

pytestmark = pytest.mark.unit


# ── IMAGE_SIZE_CONFIG ─────────────────────────────────────────────────────────

def test_image_size_config_exteranal_typo_present():
    """Regression: EXTERANAL (legacy typo) must exist to handle old PPTX templates."""
    from services.report_generator import IMAGE_SIZE_CONFIG
    assert "EXTERANAL" in IMAGE_SIZE_CONFIG
    assert IMAGE_SIZE_CONFIG["EXTERANAL"] is None  # auto-detect mode

def test_image_size_config_external_present():
    from services.report_generator import IMAGE_SIZE_CONFIG
    assert "EXTERNAL" in IMAGE_SIZE_CONFIG
    assert IMAGE_SIZE_CONFIG["EXTERNAL"] is None

def test_image_size_config_xray_dimensions():
    """X-RAY must be exactly 0.82 x 0.82 in — verified against template."""
    from services.report_generator import IMAGE_SIZE_CONFIG
    w, h, m = IMAGE_SIZE_CONFIG["XRAY"]
    assert w == pytest.approx(0.82)
    assert h == pytest.approx(0.82)

def test_image_size_config_decap_dimensions():
    """DECAP must be exactly 0.98 x 0.80 in."""
    from services.report_generator import IMAGE_SIZE_CONFIG
    w, h, m = IMAGE_SIZE_CONFIG["DECAP"]
    assert w == pytest.approx(0.98)
    assert h == pytest.approx(0.80)

def test_image_size_config_delam_dimensions():
    from services.report_generator import IMAGE_SIZE_CONFIG
    w, h, m = IMAGE_SIZE_CONFIG["DELAM"]
    assert w == pytest.approx(2.80)
    assert h == pytest.approx(1.30)

def test_image_size_config_imc_dimensions():
    from services.report_generator import IMAGE_SIZE_CONFIG
    w, h, m = IMAGE_SIZE_CONFIG["IMC"]
    assert w == pytest.approx(0.90)
    assert h == pytest.approx(0.90)


# ── _translate_image_path ─────────────────────────────────────────────────────

def test_translate_path_win_to_mount(monkeypatch):
    monkeypatch.setenv("IMAGE_WIN_ROOT",   r"D:\Auto_detect\Result")
    monkeypatch.setenv("IMAGE_MOUNT_ROOT", "/mnt/result")
    import importlib
    import services.report_generator as rg
    importlib.reload(rg)  # pick up new env vars

    result = rg._translate_image_path(r"D:\Auto_detect\Result\PR2024001\img.jpg")
    assert result == "/mnt/result/PR2024001/img.jpg"

def test_translate_path_none_returns_none():
    from services.report_generator import _translate_image_path
    assert _translate_image_path(None) is None

def test_translate_path_non_win_root_unchanged():
    from services.report_generator import _translate_image_path
    path = "/some/other/path/file.jpg"
    assert _translate_image_path(path) == path


# ── _identify_slide_category ──────────────────────────────────────────────────

def _make_slide_with_text(text: str):
    """Build a minimal mock slide whose first shape has the given text."""
    shape = MagicMock()
    shape.has_text_frame = True
    shape.text = text

    slide = MagicMock()
    slide.shapes = [shape]
    return slide


def test_identify_slide_sem_records_returns_cross_section():
    """
    Regression (2026-05-25): {sem_records.*} must map to 'CROSS SECTION INSPECTION'
    not 'IMAGE' or None.
    """
    from services.report_generator import DPAReportGenerator
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {
        "EXTERNAL": "EXTERNAL VISUAL",
        "EXTERANAL": "EXTERNAL VISUAL",
        "XRAY": "X-RAY",
        "DELAM": "DELAM",
        "DECAP": "DECAP",
        "IMC": "IMC",
        "CR": "C-R",
        "C-R": "C-R",
        "BS": "BS,WP,SP",
    }
    slide = _make_slide_with_text("{sem_records.image_1_B1-1}")
    result = gen._identify_slide_category(slide)
    assert result == "CROSS SECTION INSPECTION"

def test_identify_slide_sem_magnification_returns_cross_section():
    from services.report_generator import DPAReportGenerator
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {}
    slide = _make_slide_with_text("{sem_records.magnification_1_1}")
    result = gen._identify_slide_category(slide)
    assert result == "CROSS SECTION INSPECTION"

def test_identify_slide_image_records_xray():
    from services.report_generator import DPAReportGenerator
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {"XRAY": "X-RAY"}
    slide = _make_slide_with_text("{Image_records.XRAY_1}")
    result = gen._identify_slide_category(slide)
    assert result == "X-RAY"

def test_identify_slide_no_placeholder_returns_none():
    from services.report_generator import DPAReportGenerator
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {}
    slide = _make_slide_with_text("Some title text")
    result = gen._identify_slide_category(slide)
    assert result is None


# ── _map_placeholder_to_value ─────────────────────────────────────────────────

def _make_generator_with_data(metadata=None, imc=None, sem=None):
    from services.report_generator import DPAReportGenerator
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen.db_data = {
        "metadata":    metadata or {},
        "imc":         imc or [],
        "sem_records": sem or [],
        "images":      {},
    }
    gen.current_sem_page = 0
    gen.unique_units = []
    return gen


def test_map_placeholder_background_info():
    gen = _make_generator_with_data(
        metadata={"customer_name": "MT0"}
    )
    result = gen._map_placeholder_to_value("{background_info.customer_name}")
    assert result == "MT0"

def test_map_placeholder_excel_file_name_strips_extension():
    gen = _make_generator_with_data(
        metadata={"excel_file_name": "PR2024001.xlsx"}
    )
    result = gen._map_placeholder_to_value("{excel_file_name}")
    assert result == "PR2024001"

def test_map_placeholder_imc_value():
    gen = _make_generator_with_data(
        imc=[{"unit_id": "1-1", "imc_percent": 93.35}]
    )
    result = gen._map_placeholder_to_value("{values_records.IMC_1_1}")
    assert "93.35" in result

def test_map_placeholder_unknown_returns_empty():
    gen = _make_generator_with_data()
    text = "{unknown_table.unknown_column}"
    assert gen._map_placeholder_to_value(text) == ""

def test_map_placeholder_no_braces_unchanged():
    gen = _make_generator_with_data()
    assert gen._map_placeholder_to_value("plain text") == "plain text"

def test_map_placeholder_multiple_in_one_string():
    gen = _make_generator_with_data(
        metadata={"customer_name": "MT0", "package_type": "QFN"}
    )
    result = gen._map_placeholder_to_value(
        "{background_info.customer_name} / {background_info.package_type}"
    )
    assert result == "MT0 / QFN"


# ── _get_image_dimensions cache ───────────────────────────────────────────────

def test_get_image_dimensions_returns_fallback_for_missing(tmp_path):
    from services.report_generator import _get_image_dimensions
    _get_image_dimensions.cache_clear()
    result = _get_image_dimensions(str(tmp_path / "nonexistent.jpg"))
    assert result == (1, 1)

def test_get_image_dimensions_caches_result(tmp_path):
    """Second call must use cache (no file access)."""
    from services.report_generator import _get_image_dimensions
    _get_image_dimensions.cache_clear()

    path = str(tmp_path / "missing.jpg")
    r1 = _get_image_dimensions(path)
    r2 = _get_image_dimensions(path)
    assert r1 == r2
    info = _get_image_dimensions.cache_info()
    assert info.hits >= 1
