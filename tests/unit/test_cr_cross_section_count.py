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


def test_sql_filter_excludes_cross_section_from_cr_valid_count(mock_db):
    """
    Both tests above only exercise the Python-side `next()` predicate and
    `get_category_priority` against canned tuples — the actual SQL text sent
    to PostgreSQL for `cr_valid_count`'s FILTER clause is never inspected.
    This test captures the SQL string passed to `cur.execute(...)` for the
    aggregate query and asserts the `NOT LIKE '%%CROSS%%'` exclusion is
    actually present, in the `cr_valid_count` FILTER clause specifically
    (not just anywhere in the query).
    """
    from services.product_request_service import list_timepoint_folders

    conn, cur = mock_db
    cur.fetchall.return_value = [
        ("6.C-R", 4, 0, 4),
    ]
    cur.fetchone.return_value = (0, 0, 3)

    with patch(
        "services.product_request_service.find_bond_ability_excel",
        return_value=None,
    ):
        list_timepoint_folders("PR2024001", "T0", "MTDQS0906.1")

    # Find the call whose SQL text builds cr_valid_count (the aggregate query).
    aggregate_sql = next(
        call.args[0]
        for call in cur.execute.call_args_list
        if "cr_valid_count" in call.args[0]
    )

    # Isolate the cr_valid_count FILTER clause and assert the CROSS exclusion
    # is present inside it (not merely present somewhere else in the query).
    filter_start = aggregate_sql.index("cr_valid_count")
    # The FILTER clause for cr_valid_count precedes its own alias; walk back
    # to the start of that FILTER(...) block.
    clause_start = aggregate_sql.rindex("COUNT(*) FILTER", 0, filter_start)
    cr_valid_clause = aggregate_sql[clause_start:filter_start]

    assert "NOT LIKE '%%CROSS%%'" in cr_valid_clause
    assert "C-R" in cr_valid_clause or "CR" in cr_valid_clause
