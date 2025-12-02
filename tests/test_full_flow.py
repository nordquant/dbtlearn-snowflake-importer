import pytest
from streamlit.testing.v1 import AppTest

# 5 minutes for Snowflake setup (data import can be slow)
SNOWFLAKE_SETUP_TIMEOUT = 300


class TestFullSetupFlow:
    """Test the complete Streamlit app flow using AppTest."""

    def test_complete_setup_flow(self, snowflake_credentials):
        """
        Test the full setup flow:
        1. Start setup
        2. Generate keys
        3. Enter Snowflake credentials
        4. Run Snowflake setup (creates users, imports data)
        5. Verify we reach the download step
        """
        # Initialize the app
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Verify app started without errors
        assert not at.exception, f"App failed to start: {at.exception}"

        # Step 0 -> Step 1: Click "Start Setup Process"
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step == 1

        # Step 1: Keys should be auto-generated
        assert "keypair" in at.session_state, "Keypair should be generated"

        # Step 1 -> Step 2: Click "Continue to Snowflake Setup"
        at.button(key="btn_continue_to_snowflake").click().run()
        assert at.session_state.step == 2

        # Step 2: Enter Snowflake credentials
        at.text_input(key="input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.text_input(key="input_snowflake_username").set_value(
            snowflake_credentials["username"]
        )
        at.text_input(key="input_snowflake_password").set_value(
            snowflake_credentials["password"]
        )
        at.run()

        # Click "Start Setup" - this runs the full Snowflake setup
        # Use longer timeout for Snowflake operations
        at.button(key="btn_start_snowflake_setup").click().run(
            timeout=SNOWFLAKE_SETUP_TIMEOUT
        )

        # Verify no exceptions or errors
        assert not at.exception, f"Snowflake setup raised exception: {at.exception}"

        # Check for errors - if there are any, show what went wrong
        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Snowflake setup showed errors: {error_messages}")

        # Verify we reached step 3 (download configuration files)
        assert at.session_state.step == 3, (
            f"Expected step 3, got step {at.session_state.step}"
        )

        # Verify keypair and account are in session state (needed for downloads)
        assert "keypair" in at.session_state, "Keypair should be in session state"
        assert "snowflake_account" in at.session_state, "Account should be in session state"

        # Note: download_button is not supported by Streamlit AppTest framework
        # We verify step 3 is reached, which means download buttons are rendered
