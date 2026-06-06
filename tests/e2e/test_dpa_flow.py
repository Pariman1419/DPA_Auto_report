"""
End-to-End (E2E) UI tests for the DPA React frontend application.
Uses Playwright and pytest-playwright.
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def base_url():
    """Vite dev server URL in the sandbox environment."""
    return "http://localhost:5190"


def test_dpa_login_gate_redirection(page: Page, base_url: str):
    """
    E2E: Unauthenticated users should be gated by the Login screen,
    which asks for an Employee ID and password.
    """
    page.goto(base_url)
    
    # Assert we are on the login page and show the header title
    expect(page.locator("text=DPA QA Manager")).to_be_visible()
    expect(page.locator("text=Automated Reporting Pipeline")).to_be_visible()
    
    # Check that inputs exist
    expect(page.get_by_placeholder("e.g. 10455")).to_be_visible()
    expect(page.get_by_placeholder("••••••••")).to_be_visible()


def test_dpa_login_validation_failures(page: Page, base_url: str):
    """
    E2E: Submitting the login form with empty inputs displays a validation error.
    """
    page.goto(base_url)
    
    # Click Sign In without entering credentials
    page.get_by_role("button", name="Sign In →").click()
    
    # Assert validation error message is rendered
    expect(page.locator("text=Please enter both Employee ID and password")).to_be_visible()


def test_dpa_full_report_generation_wizard_workflow(page: Page, base_url: str):
    """
    E2E: Full end-to-end report generation flow.
    1. Log in successfully.
    2. Load Create Report page (Wizard Step 1: Select PR).
    3. Verify and load detailed tables (Wizard Step 2: Verify data).
    4. Select categories and click generate (Wizard Step 3: Compile PPTX).
    5. Assert generation success message.
    6. Navigate to history and download file.
    7. Logout.
    """
    # ── Step 1: Login ──────────────────────────────────────────────────────────
    page.goto(base_url)
    
    # Enter credentials
    page.get_by_placeholder("e.g. 10455").fill("EMP001")
    page.get_by_placeholder("••••••••").fill("test1234")
    
    # Mocking API calls is done below if E2E is run against mock server.
    # Submit login
    page.get_by_role("button", name="Sign In →").click()
    
    # Expect transition to main app - Sidebar should be visible
    expect(page.locator("text=QA Engineer")).to_be_visible()
    expect(page.locator("text=Create Report")).to_be_visible()

    # ── Step 2: Wizard Step 1 - Select PR ─────────────────────────────────────
    # Select PR from dropdown selector
    # Playwright clicks on the dropdown select trigger
    page.get_by_role("combobox").click()
    # Click on the PR2024001 item in the dropdown
    page.get_by_role("option", name="PR2024001").click()
    
    # Click Next to advance
    page.get_by_role("button", name="Next Step →").click()

    # ── Step 3: Wizard Step 2 - Verify Data ───────────────────────────────────
    # Expect data inspection tables to be rendered
    expect(page.locator("text=Verify Test Details")).to_be_visible()
    expect(page.locator("text=BOM & Materials")).to_be_visible()
    
    # We should see the IMC and SEM records
    expect(page.locator("text=IMC Measurements")).to_be_visible()
    expect(page.locator("text=CROSS SECTION")).to_be_visible()
    
    # Verify values exist
    expect(page.locator("text=MTDQS0906.1")).to_be_visible()  # Order Lot
    expect(page.locator("text=Ag Paste")).to_be_visible()       # Die Attach Material

    # Click Next
    page.get_by_role("button", name="Proceed to Sections →").click()

    # ── Step 4: Wizard Step 3 - Compile PPTX ──────────────────────────────────
    # Check selection checkboxes for PPTX slides
    expect(page.locator("text=Select Report Sections")).to_be_visible()
    
    # Toggling checkboxes
    page.get_by_label("1.EXTERNAL VISUAL").check()
    page.get_by_label("3.X-RAY").check()
    page.get_by_label("4.DECAP").check()
    
    # Click "Compile PowerPoint"
    page.get_by_role("button", name="Generate PPTX Report →").click()

    # ── Step 5: Assert Success ───────────────────────────────────────────────
    # We expect report generated successfully banner
    expect(page.locator("text=Report Generated Successfully!")).to_be_visible()
    expect(page.locator("text=DPA_Report_PR2024001")).to_be_visible()
    
    # Check download report button is present
    expect(page.get_by_role("button", name="Download File")).to_be_visible()

    # ── Step 6: Navigation to History and Download ────────────────────────────
    # Go to History page via Sidebar nav
    page.get_by_role("link", name="History").click()
    expect(page.locator("text=Generation History")).to_be_visible()
    
    # Check historical record row is visible
    expect(page.locator("text=PR2024001")).to_be_visible()
    
    # Initiate Playwright download handler
    with page.expect_download() as download_info:
        # Click download icon/button in the first row
        page.get_by_role("button", name="Download").first.click()
    download = download_info.value
    
    # Assert download name format matches
    assert "DPA_Report_PR2024001" in download.suggested_filename
    assert download.suggested_filename.endswith(".pptx")

    # ── Step 7: Logout ────────────────────────────────────────────────────────
    page.get_by_role("button", name="Log Out").click()
    
    # We should be redirected back to the login screen
    expect(page.locator("text=DPA QA Manager")).to_be_visible()
