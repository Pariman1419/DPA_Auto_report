"""
Regression test for the CR / Cross-Section Inspection count bug.

Bug: "CR" is a substring of "CROSS", so a loose LIKE '%CR%' / "CR" in x
match can pick up a "CROSS SECTION INSPECTION" row when computing the
C-R (destructive cross-section) valid file count. The display-assignment
loop already excludes "CROSS" (product_request_service.py ~line 455);
this test targets the earlier point in the same function where the
substring bug can still leak through, independent of row order.
"""
import pytest
from unittest.mock import patch

pytestmark = pytest.mark.unit


def test_cross_section_row_does_not_pollute_cr_count(mock_db):
    """
    Seed a CROSS SECTION INSPECTION row ahead of the real 6.C-R row
    (reversed from alphabetical order) and assert the C-R file count
    comes from the true C-R row, not the CROSS row.
    """
    from services.product_request_service import list_timepoint_folders

    conn, cur = mock_db
    # (category, file_count, imc_valid_count, cr_valid_count)
    # CROSS row deliberately listed FIRST so a buggy `next()` without a
    # "CROSS" exclusion would pick its cr_valid_count (99) instead of
    # the real 6.C-R row's (4).
    cur.fetchall.return_value = [
        ("CROSS SECTION INSPECTION", 12, 0, 99),
        ("6.C-R", 4, 0, 4),
    ]
    cur.fetchone.return_value = (0, 0, 3)  # imc_count, bond_count, sem_count

    with patch(
        "services.product_request_service.find_bond_ability_excel",
        return_value=None,
    ):
        folders = list_timepoint_folders("PR2024001", "T0", "MTDQS0906.1")

    cr_folder = next(f for f in folders if f["name"] == "6.C-R")
    assert cr_folder["fileCount"] == 4

    cross_folder = next(
        f for f in folders if f["name"] == "CROSS SECTION INSPECTION"
    )
    assert cross_folder["fileCount"] == 12  # its own file_count, untouched


def test_cross_section_sorts_separately_from_cr(mock_db):
    """CROSS SECTION INSPECTION must not share the C-R sort bucket."""
    from services.product_request_service import list_timepoint_folders

    conn, cur = mock_db
    cur.fetchall.return_value = [
        ("CROSS SECTION INSPECTION", 12, 0, 99),
        ("6.C-R", 4, 0, 4),
    ]
    cur.fetchone.return_value = (0, 0, 3)

    with patch(
        "services.product_request_service.find_bond_ability_excel",
        return_value=None,
    ):
        folders = list_timepoint_folders("PR2024001", "T0", "MTDQS0906.1")

    names_in_order = [f["name"] for f in folders]
    # 6.C-R (priority 6) must come before CROSS SECTION INSPECTION (priority 8)
    assert names_in_order.index("6.C-R") < names_in_order.index("CROSS SECTION INSPECTION")
