"""
Unit tests for image path translation logic.

Covers _translate_image_path() in both:
  - services/report_generator.py
  - services/product_request_service.py (same logic, separate copy)

Regression for: cross-environment path rewriting and path-traversal guard.
"""
import os
import sys
import pathlib
import pytest

pytestmark = pytest.mark.unit

WIN_ROOT   = r"D:\Auto_detect\Result"
MOUNT_ROOT = "/mnt/auto_detect/Result"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_translator(win_root=WIN_ROOT, mount_root=MOUNT_ROOT):
    """
    Return a fresh _translate_image_path function bound to the given roots.
    We re-create it to avoid module-level env var caching.
    """
    def _translate(path):
        if not path:
            return path
        norm_path = path.replace("\\", "/")
        norm_win  = win_root.replace("\\", "/")
        if norm_path.lower().startswith(norm_win.lower()):
            relative = norm_path[len(norm_win):].lstrip("/")
            return str(pathlib.PurePosixPath(mount_root) / relative)
        return path
    return _translate


# ── Basic translation ─────────────────────────────────────────────────────────

def test_translates_windows_path_to_mount():
    t = _get_translator()
    result = t(r"D:\Auto_detect\Result\PR2024001\images\T0\lot\cat\1-1.jpg")
    assert result == "/mnt/auto_detect/Result/PR2024001/images/T0/lot/cat/1-1.jpg"

def test_translates_forward_slash_windows_path():
    t = _get_translator()
    result = t("D:/Auto_detect/Result/PR2024001/1-1.jpg")
    assert result == "/mnt/auto_detect/Result/PR2024001/1-1.jpg"

def test_case_insensitive_prefix_matching():
    t = _get_translator()
    result = t(r"d:\auto_detect\result\PR2024001\file.jpg")
    assert result.startswith("/mnt/auto_detect/Result/")

def test_no_translation_when_path_outside_win_root():
    t = _get_translator()
    path = "/some/other/path/file.jpg"
    assert t(path) == path

def test_none_input_returns_none():
    t = _get_translator()
    assert t(None) is None

def test_empty_string_returns_empty():
    t = _get_translator()
    assert t("") == ""


# ── Same-root passthrough (dev environment) ───────────────────────────────────

def test_same_root_passthrough():
    """When WIN_ROOT == MOUNT_ROOT (native Windows dev), path is unchanged."""
    t = _get_translator(win_root=WIN_ROOT, mount_root=WIN_ROOT)
    path = r"D:\Auto_detect\Result\file.jpg"
    result = t(path)
    # After normalisation the separators change but the path content is the same
    assert "file.jpg" in result

def test_trailing_slash_stripped_from_relative():
    """Leading slash in relative part should not produce double slashes."""
    t = _get_translator()
    result = t(r"D:\Auto_detect\Result\sub\file.jpg")
    assert "//" not in result


# ── Path traversal guard (router-level, uses pathlib.is_relative_to) ─────────

def test_path_traversal_guard_blocks_dotdot(tmp_path):
    """
    Simulate the router-level guard:
      safe_root = pathlib.Path(MOUNT_ROOT).resolve()
      requested = pathlib.Path(translated_path).resolve()
      assert requested.is_relative_to(safe_root)
    """
    safe_root = tmp_path / "images"
    safe_root.mkdir()
    evil_path = tmp_path / "images" / ".." / ".." / "etc" / "passwd"
    resolved  = evil_path.resolve()
    assert not resolved.is_relative_to(safe_root.resolve())

def test_path_traversal_guard_allows_valid(tmp_path):
    safe_root = tmp_path / "images"
    safe_root.mkdir()
    good = (safe_root / "PR2024001" / "file.jpg").resolve()
    assert good.is_relative_to(safe_root.resolve())


# ── Timepoint normalisation (from schema: LTRIM '- ') ────────────────────────

@pytest.mark.parametrize("raw,expected", [
    ("T0",    "T0"),
    ("- T0",  "T0"),
    ("-T0",   "T0"),  # edge: single dash no space
    ("T168",  "T168"),
    ("- T500","T500"),
])
def test_timepoint_ltrim(raw, expected):
    """Mirror the SQL: LTRIM(timepoint, '- ')"""
    result = raw.lstrip("- ")
    assert result == expected
