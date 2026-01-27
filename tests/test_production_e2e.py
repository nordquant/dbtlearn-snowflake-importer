"""
End-to-end test for the production deployment at dbtsetup.nordquant.com.

This test uses Playwright to simulate a real user going through the complete
Snowflake setup flow, verifying the deployed service is working correctly.

Run locally:
    uv run playwright install chromium
    uv run pytest tests/test_production_e2e.py -v -s

Environment variables required:
    SNOWFLAKE_ACCOUNT - Snowflake account identifier
    SNOWFLAKE_USERNAME - Snowflake admin username
    SNOWFLAKE_PASSWORD - Snowflake admin password

Optional:
    PRODUCTION_URL - Override the default production URL
    CF_ACCESS_CLIENT_ID - Cloudflare Access client ID (if site is protected)
    CF_ACCESS_CLIENT_SECRET - Cloudflare Access client secret (if site is protected)
"""

import os
import pytest
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeout


PRODUCTION_URL = os.environ.get("PRODUCTION_URL", "https://dbtsetup.nordquant.com")

# Timeout for Snowflake setup operations (5 minutes)
SNOWFLAKE_SETUP_TIMEOUT = 300_000  # milliseconds

# Timeout for page loads and UI interactions
PAGE_TIMEOUT = 30_000  # milliseconds


@pytest.fixture(scope="module")
def browser_context():
    """Create a browser context for the test session."""
    with sync_playwright() as p:
        # Launch browser in headless mode for CI
        browser = p.chromium.launch(headless=True)

        # Create context with Cloudflare Access headers if provided
        context_options = {
            "viewport": {"width": 1280, "height": 720},
        }

        # Add Cloudflare Access Service Token headers if available
        cf_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
        cf_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")

        if cf_client_id and cf_client_secret:
            context_options["extra_http_headers"] = {
                "CF-Access-Client-Id": cf_client_id,
                "CF-Access-Client-Secret": cf_client_secret,
            }
            print(f"Using Cloudflare Access Service Token for authentication")

        context = browser.new_context(**context_options)
        context.set_default_timeout(PAGE_TIMEOUT)

        yield context

        context.close()
        browser.close()


@pytest.fixture
def snowflake_credentials():
    """Load Snowflake credentials from environment variables."""
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    username = os.environ.get("SNOWFLAKE_USERNAME")
    password = os.environ.get("SNOWFLAKE_PASSWORD")

    if not all([account, username, password]):
        pytest.skip(
            "Snowflake credentials not provided. "
            "Set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USERNAME, SNOWFLAKE_PASSWORD"
        )

    return {
        "account": account,
        "username": username,
        "password": password,
    }


class TestProductionE2E:
    """End-to-end tests for the production deployment."""

    def test_site_is_accessible(self, browser_context):
        """Test that the production site loads and shows expected content."""
        page = browser_context.new_page()

        try:
            print(f"\nNavigating to {PRODUCTION_URL}...")
            response = page.goto(PRODUCTION_URL, wait_until="networkidle")

            # Check for Cloudflare challenge page
            if "Just a moment" in page.content() or "Checking your browser" in page.content():
                pytest.fail(
                    "Cloudflare is blocking access. "
                    "Set CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET environment variables."
                )

            assert response.status == 200, f"Expected status 200, got {response.status}"

            # Verify page contains expected content
            page.wait_for_selector("text=Snowflake", timeout=PAGE_TIMEOUT)
            print("Site is accessible and shows Snowflake content")

        finally:
            page.close()

    def test_complete_setup_flow(self, browser_context, snowflake_credentials):
        """
        Test the complete Snowflake setup flow on production.

        Steps:
        1. Navigate to production site
        2. Click "Start Setup Process"
        3. Click "Continue to Snowflake Setup"
        4. Enter Snowflake credentials
        5. Click "Start Setup"
        6. Wait for setup to complete
        7. Verify we reach the download configuration step
        """
        page = browser_context.new_page()

        try:
            # Step 1: Navigate to production site
            print(f"\n=== Starting E2E test against {PRODUCTION_URL} ===")
            print("Step 1: Navigating to production site...")
            page.goto(PRODUCTION_URL, wait_until="networkidle")

            # Check for Cloudflare challenge
            if "Just a moment" in page.content():
                pytest.fail(
                    "Cloudflare is blocking access. "
                    "Configure CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET."
                )

            # Verify we're on the landing page
            page.wait_for_selector("text=Snowflake", timeout=PAGE_TIMEOUT)
            print("Landing page loaded successfully")

            # Step 2: Click "Start Setup Process"
            print("Step 2: Clicking 'Start Setup Process'...")
            start_button = page.get_by_role("button", name="Start Setup Process")
            start_button.click()

            # Wait for step 1 (key generation) to appear
            page.wait_for_selector("text=Generate Snowflake Access Keys", timeout=PAGE_TIMEOUT)
            print("Key generation step reached")

            # Step 3: Click "Continue to Snowflake Setup"
            print("Step 3: Clicking 'Continue to Snowflake Setup'...")
            continue_button = page.get_by_role("button", name="Continue to Snowflake Setup")
            continue_button.click()

            # Wait for Snowflake setup form to appear
            page.wait_for_selector("text=Snowflake Setup", timeout=PAGE_TIMEOUT)
            print("Snowflake setup form loaded")

            # Step 4: Enter Snowflake credentials
            print("Step 4: Entering Snowflake credentials...")

            # Streamlit renders text inputs with labels above them
            # We use get_by_label which matches aria-label attributes
            # The inputs are in order: account, username, password

            # Get all visible text inputs (non-password)
            text_inputs = page.locator("input[type='text']:visible").all()
            if len(text_inputs) >= 2:
                # First text input is account
                text_inputs[0].fill(snowflake_credentials["account"])
                # Second text input is username
                text_inputs[1].fill(snowflake_credentials["username"])
            else:
                pytest.fail(f"Expected at least 2 text inputs, found {len(text_inputs)}")

            # Password input
            password_input = page.locator("input[type='password']").first
            password_input.fill(snowflake_credentials["password"])

            print(f"Credentials entered for account: {snowflake_credentials['account']}")

            # Step 5: Click "Start Setup"
            print("Step 5: Clicking 'Start Setup'...")
            setup_button = page.get_by_role("button", name="Start Setup")
            setup_button.click()

            # Step 6: Wait for setup to complete
            print("Step 6: Waiting for Snowflake setup to complete (this may take a few minutes)...")

            # Poll for completion - check for success OR error states
            # The setup can take up to 5 minutes
            max_wait_seconds = SNOWFLAKE_SETUP_TIMEOUT // 1000
            poll_interval_seconds = 5

            for elapsed in range(0, max_wait_seconds, poll_interval_seconds):
                # Check for success - we reach step 3 (Download Configuration Files)
                download_header = page.locator("text=Download Configuration Files")
                if download_header.count() > 0 and download_header.is_visible():
                    print(f"Setup completed successfully after ~{elapsed}s!")
                    break

                # Check for error messages in Streamlit alerts
                error_alerts = page.locator("[data-testid='stAlert']").all()
                for alert in error_alerts:
                    alert_text = alert.text_content()
                    if "Error" in alert_text or "error" in alert_text:
                        pytest.fail(f"Setup failed with error: {alert_text}")

                # Check for Streamlit exception display
                exception_display = page.locator("[data-testid='stException']")
                if exception_display.count() > 0:
                    exception_text = exception_display.text_content()
                    pytest.fail(f"Setup raised exception: {exception_text}")

                # Wait before next poll
                page.wait_for_timeout(poll_interval_seconds * 1000)

                if elapsed % 30 == 0 and elapsed > 0:
                    print(f"  Still waiting... ({elapsed}s elapsed)")
            else:
                # Timeout - capture current state
                screenshot_path = f"/tmp/e2e_timeout_{os.getpid()}.png"
                page.screenshot(path=screenshot_path)
                pytest.fail(
                    f"Setup timed out after {max_wait_seconds}s. "
                    f"Screenshot saved to {screenshot_path}"
                )

            # Step 7: Verify we reached the download step
            print("Step 7: Verifying download configuration step...")

            # Check for download buttons or step 3 content
            download_content = page.locator("text=Download Configuration Files")
            expect(download_content).to_be_visible(timeout=PAGE_TIMEOUT)

            # Verify download buttons exist (Streamlit download buttons)
            # The buttons have text containing "Download"
            download_buttons = page.locator("button:has-text('Download')").all()
            assert len(download_buttons) >= 2, f"Expected at least 2 download buttons, found {len(download_buttons)}"

            print("=== E2E test completed successfully! ===")

        except Exception as e:
            # Take screenshot on failure for debugging
            screenshot_path = f"/tmp/e2e_failure_{os.getpid()}.png"
            try:
                page.screenshot(path=screenshot_path)
                print(f"Screenshot saved to {screenshot_path}")
            except Exception:
                pass

            # Print page content for debugging
            print(f"Page URL: {page.url}")
            print(f"Page title: {page.title()}")
            raise

        finally:
            page.close()


def test_quick_health_check():
    """
    Quick health check that doesn't require Snowflake credentials.
    Verifies the site is up and responding.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        context_options = {"viewport": {"width": 1280, "height": 720}}

        # Add Cloudflare Access headers if available
        cf_client_id = os.environ.get("CF_ACCESS_CLIENT_ID")
        cf_client_secret = os.environ.get("CF_ACCESS_CLIENT_SECRET")
        if cf_client_id and cf_client_secret:
            context_options["extra_http_headers"] = {
                "CF-Access-Client-Id": cf_client_id,
                "CF-Access-Client-Secret": cf_client_secret,
            }

        context = browser.new_context(**context_options)
        page = context.new_page()

        try:
            print(f"\nQuick health check for {PRODUCTION_URL}...")
            response = page.goto(PRODUCTION_URL, timeout=30000)

            # Check for Cloudflare block
            content = page.content()
            if "Just a moment" in content or "Checking your browser" in content:
                pytest.fail(
                    "Cloudflare is blocking automated access. "
                    "Configure CF_ACCESS_CLIENT_ID and CF_ACCESS_CLIENT_SECRET."
                )

            assert response.status == 200

            # Wait for Streamlit app to fully load (it loads content dynamically)
            # The app shows "Snowflake" in the welcome message once loaded
            print("Waiting for Streamlit app to load...")
            page.wait_for_selector("text=Snowflake", timeout=30000)

            print("Health check passed!")

        finally:
            page.close()
            context.close()
            browser.close()
