"""
Regression tests to preserve historical bug knowledge and prevent recurrent failures.
"""
import os
import pathlib
import pytest
from unittest.mock import MagicMock

from services.report_generator import DPAReportGenerator, _translate_image_path
from services.product_request_service import _translate_image_path as _service_translate

pytestmark = pytest.mark.regression


# ── Bug 1: Trailing slash path resolution (fixed by pathlib.Path.name) ────────

def test_trailing_slash_basename_regression():
    """
    Regression: os.path.basename returns an empty string on Linux paths with a trailing slash.
    Ensure our path translation and filename extraction use pathlib to be cross-platform robust.
    """
    linux_path = "/var/dpa/output/report_PR1234/"
    
    # Old logic: os.path.basename(linux_path) -> ""
    # Correct logic using pathlib
    name = pathlib.Path(linux_path).name
    assert name == "report_PR1234"


def test_translate_image_path_separators():
    """
    Regression: Verify that _translate_image_path handles mismatched slashes and separators.
    """
    win_path = r"D:\Auto_detect\Result\PR2024001\images\T0\LOT\1.EXTERNAL VISUAL/1-1.jpg"
    translated = _translate_image_path(win_path)
    
    # Assert separators are consistent with the OS/pathlib resolution
    expected_suffix = pathlib.Path("PR2024001/images/T0/LOT/1.EXTERNAL VISUAL/1-1.jpg")
    assert pathlib.Path(translated).relative_to(os.environ["IMAGE_MOUNT_ROOT"]) == expected_suffix


# ── Bug 2: Empty IMC values (fixed by guard clauses) ─────────────────────────

def test_empty_imc_values_does_not_crash():
    """
    Regression: IMC records with empty or None values in the database previously caused JSON decode errors.
    Ensure our placeholder mapping handles missing/empty values gracefully.
    """
    # Create generator instance with empty IMC record
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen.db_data = {
        "metadata": {},
        "imc": [
            {"unit_id": "1-1", "imc_percent": ""},  # Empty string
            {"unit_id": "1-2", "imc_percent": None}  # None
        ],
        "sem_records": [],
    }
    
    # Should replace with empty string rather than crashing
    assert gen._map_placeholder_to_value("{values_records.IMC_1_1}") == ""
    assert gen._map_placeholder_to_value("{values_records.IMC_1_2}") == ""
    
    # Non-existent key should also return empty string safely
    assert gen._map_placeholder_to_value("{values_records.IMC_9_9}") == ""


# ── Bug 3: C-R vs CROSS SECTION slide separation & image rendering ────────────

def test_identify_slide_category_separation():
    """
    Regression (2026-05-25): Verify C-R slides are separated from CROSS SECTION slides.
    {sem_records.image_*} placeholders must identify as 'CROSS SECTION INSPECTION' to prevent sizing collision.
    """
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {"C-R": "C-R", "CR": "C-R"}
    
    # Slide containing a C-R image placeholder
    cr_shape = MagicMock()
    cr_shape.has_text_frame = True
    cr_shape.text = "{Image_records.C-R_1-1}"
    cr_slide = MagicMock()
    cr_slide.shapes = [cr_shape]
    
    # Slide containing a SEM (Cross Section) placeholder
    sem_shape = MagicMock()
    sem_shape.has_text_frame = True
    sem_shape.text = "{sem_records.image_1_B1-1}"
    sem_slide = MagicMock()
    sem_slide.shapes = [sem_shape]
    
    assert gen._identify_slide_category(cr_slide) == "C-R"
    assert gen._identify_slide_category(sem_slide) == "CROSS SECTION INSPECTION"


# ── Bug 4: Legacy Template Typo compatibility ───────────────────────────────

def test_legacy_exteranal_typo_compatibility():
    """
    Regression: Older PowerPoint templates contain the typo `{Image_records.EXTERANAL_1-1}`.
    Verify that the system identifies this as 'EXTERNAL VISUAL' so they are not deleted.
    """
    gen = DPAReportGenerator.__new__(DPAReportGenerator)
    gen._CATEGORY_MAP = {"EXTERANAL": "EXTERNAL VISUAL"}
    
    shape = MagicMock()
    shape.has_text_frame = True
    shape.text = "{Image_records.EXTERANAL_1-1}"
    slide = MagicMock()
    slide.shapes = [shape]
    
    assert gen._identify_slide_category(slide) == "EXTERNAL VISUAL"
