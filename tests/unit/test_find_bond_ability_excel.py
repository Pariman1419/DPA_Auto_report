"""
Smoke test for find_bond_ability_excel's glob-based rewrite.

This function is carry-forward code (entered version control for the first
time on the code-review-fixes branch, carried over from pre-existing
uncommitted work) with no prior test coverage. This is a minimal smoke test,
not exhaustive coverage — it only verifies the function doesn't crash and
returns None when the expected excel directory doesn't exist on disk.
"""
import pytest

pytestmark = pytest.mark.unit


def test_find_bond_ability_excel_returns_none_when_dir_missing(mock_db, tmp_path):
    """
    If the resolved '7.BS,WP,SP' excel directory doesn't exist on disk,
    the glob lookup must be skipped (guarded by os.path.isdir) rather than
    raising, and the function should return None.
    """
    from services.product_request_service import find_bond_ability_excel

    conn, cur = mock_db
    # image_records row whose file_path resolves (via _translate_image_path)
    # to a lot folder that does NOT contain a "7.BS,WP,SP" subfolder on disk.
    nonexistent_lot_root = tmp_path / "PR2024001" / "T0" / "MTDQS0906.1"
    fake_file_path = str(nonexistent_lot_root / "1.EXTERNAL VISUAL" / "img.jpg")
    cur.fetchone.return_value = (fake_file_path,)

    result = find_bond_ability_excel("PR2024001", "T0", "MTDQS0906.1")

    assert result is None


def test_find_bond_ability_excel_returns_none_when_no_image_records(mock_db):
    """If no image_records row exists for the PR/TP/lot, return None without crashing."""
    from services.product_request_service import find_bond_ability_excel

    conn, cur = mock_db
    cur.fetchone.return_value = None

    result = find_bond_ability_excel("PR2024001", "T0", "MTDQS0906.1")

    assert result is None
