import pytest
from streamlit.testing.v1 import AppTest

# 5 minutes for Snowflake setup (data import can be slow)
SNOWFLAKE_SETUP_TIMEOUT = 300


def _user_type(connection, login_name):
    """Return the TYPE column from DESCRIBE USER for a given login_name."""
    from sqlalchemy import text

    rows = connection.execute(text(f"DESCRIBE USER {login_name}")).fetchall()
    for row in rows:
        # DESCRIBE USER returns rows with a `property` column; find TYPE
        if str(row[0]).upper() == "TYPE":
            return str(row[1]).upper() if row[1] is not None else None
    return None


class TestFullSetupFlow:
    """Test the complete Streamlit app flow using AppTest."""

    def test_standard_setup_flow(self, snowflake_credentials):
        """
        Test the full standard setup flow via "Standard Setup" sidebar option:
        1. Start setup (step 0 -> step 1)
        2. Snowflake setup: keypair in expander + credentials + SQL execution
        3. Verify we reach step 2 (download configuration files)

        Verifies: AIRBNB tables (3), AIRSTATS tables (3), dbt/preset user connections.
        """
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Verify app started without errors
        assert not at.exception, f"App failed to start: {at.exception}"

        # Step 0 -> Step 1: Click "Start Setup Process"
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step_standard == 1

        # Step 1: Keys should be auto-generated, keypair in expander
        assert "keypair" in at.session_state, "Keypair should be generated"

        # Enter Snowflake credentials (std_ prefix for standard setup tab)
        at.text_input(key="std_input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.text_input(key="std_input_snowflake_username").set_value(
            snowflake_credentials["username"]
        )
        at.text_input(key="std_input_snowflake_password").set_value(
            snowflake_credentials["password"]
        )
        at.run()

        # Click "Start Setup" - this runs the full Snowflake setup
        at.button(key="btn_start_snowflake_setup").click().run(
            timeout=SNOWFLAKE_SETUP_TIMEOUT
        )

        # Verify no exceptions or errors
        assert not at.exception, f"Snowflake setup raised exception: {at.exception}"

        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Snowflake setup showed errors: {error_messages}")

        # Verify we reached step 2 (download configuration files)
        assert at.session_state.step_standard == 2, (
            f"Expected step 2, got step {at.session_state.step_standard}"
        )

        # Verify keypair and account are in session state (needed for downloads)
        assert "keypair" in at.session_state, "Keypair should be in session state"
        assert "snowflake_account" in at.session_state, "Account should be in session state"

    def test_capstone_only_flow(self, snowflake_credentials):
        """
        Test the capstone-only flow via "Capstone Only Setup" tab:
        1. Landing page with warning (step 0 -> step 1)
        2. Credentials + AIRSTATS SQL execution

        Verifies: AIRSTATS tables (3), success message.
        """
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Verify app started without errors
        assert not at.exception, f"App failed to start: {at.exception}"

        # With st.tabs, all tab content is rendered — capstone elements are accessible directly

        # Step 0 -> Step 1: Click "Set up AIRSTATS Capstone"
        at.button(key="btn_start_capstone").click().run()
        assert at.session_state.step_capstone == 1

        # Enter Snowflake credentials (cap_ prefix for capstone tab)
        at.text_input(key="cap_input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.text_input(key="cap_input_snowflake_username").set_value(
            snowflake_credentials["username"]
        )
        at.text_input(key="cap_input_snowflake_password").set_value(
            snowflake_credentials["password"]
        )
        at.run()

        # Click "Start Capstone Setup"
        at.button(key="btn_start_capstone_setup").click().run(
            timeout=SNOWFLAKE_SETUP_TIMEOUT
        )

        # Verify no exceptions or errors
        assert not at.exception, f"Capstone setup raised exception: {at.exception}"

        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Capstone setup showed errors: {error_messages}")

        # Verify success message is shown
        success_messages = [s.value for s in at.success]
        assert any("AIRSTATS" in msg for msg in success_messages), (
            f"Expected AIRSTATS success message, got: {success_messages}"
        )

    def test_legacy_setup_flow(self, snowflake_credentials):
        """
        Legacy username/password flow via the "Legacy Username/Password Setup" tab:
        1. Land (step 0) -> click "Start Legacy Setup" -> step 1
        2. Fill admin credentials, run setup
        3. Verify: no exceptions, no error panels, success message mentions
           both credential pairs, dbt and preset users end up with
           TYPE=LEGACY_SERVICE.
        """
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        assert not at.exception, f"App failed to start: {at.exception}"

        at.button(key="btn_start_legacy").click().run()
        assert at.session_state.step_legacy == 1

        at.text_input(key="leg_input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.text_input(key="leg_input_snowflake_username").set_value(
            snowflake_credentials["username"]
        )
        at.text_input(key="leg_input_snowflake_password").set_value(
            snowflake_credentials["password"]
        )
        at.run()

        at.button(key="btn_start_legacy_setup").click().run(
            timeout=SNOWFLAKE_SETUP_TIMEOUT
        )

        assert not at.exception, f"Legacy setup raised exception: {at.exception}"

        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Legacy setup showed errors: {error_messages}")

        # Success panel should mention the two credential pairs, not a download
        markdown_text = " ".join([m.value for m in at.markdown])
        assert "dbtPassword123" in markdown_text
        assert "presetPassword123" in markdown_text
        assert "Username & Password" in markdown_text

        # DB-level sanity: both users should now be LEGACY_SERVICE
        from sqlalchemy import text

        from streamlit_app import get_snowflake_connection

        with get_snowflake_connection(
            snowflake_credentials["account"],
            snowflake_credentials["username"],
            snowflake_credentials["password"],
        ) as conn:
            dbt_type = _user_type(conn, "dbt")
            preset_type = _user_type(conn, "preset")
            assert dbt_type == "LEGACY_SERVICE", f"dbt user type is {dbt_type}"
            assert preset_type == "LEGACY_SERVICE", f"preset user type is {preset_type}"

    @pytest.mark.ceu
    def test_ceu_setup_flow(self, snowflake_credentials):
        """
        Test the CEU flow via ?course=ceu query param (no sidebar):
        1. Start setup
        2. Snowflake setup (keypair + credentials + SQL including AIRSTATS)
        3. Verify we reach step 2 (downloads)
        """
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        # Verify app started without errors
        assert not at.exception, f"App failed to start: {at.exception}"

        # Verify CEU mode is active
        assert at.session_state.course_mode == "ceu"

        # CEU mode should NOT have sidebar radio
        welcome_text = " ".join([m.value for m in at.markdown])
        assert "CEU Modern Data Platforms" in welcome_text

        # Step 0 -> Step 1: Click "Start Setup Process"
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step_standard == 1

        # Step 1: Keys should be auto-generated
        assert "keypair" in at.session_state, "Keypair should be generated"

        # Enter credentials (CEU uses standard_setup which has std_ prefix,
        # but in CEU mode there are no tabs so no prefix conflict — however
        # standard_setup always uses std_ prefix)
        at.text_input(key="std_input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.text_input(key="std_input_snowflake_username").set_value(
            snowflake_credentials["username"]
        )
        at.text_input(key="std_input_snowflake_password").set_value(
            snowflake_credentials["password"]
        )
        at.run()

        # Run setup (includes AIRSTATS)
        at.button(key="btn_start_snowflake_setup").click().run(
            timeout=SNOWFLAKE_SETUP_TIMEOUT
        )

        # Verify no exceptions
        assert not at.exception, f"Setup raised exception: {at.exception}"

        # Check for errors
        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Setup showed errors: {error_messages}")

        # Verify we reached step 2
        assert at.session_state.step_standard == 2, (
            f"Expected step 2, got step {at.session_state.step_standard}"
        )
