import pytest
from streamlit.testing.v1 import AppTest


class TestCourseModeDetection:
    """Test course mode detection from query parameters."""

    def test_default_mode_welcome_message(self):
        """Default mode shows standard dbt Bootcamp welcome with AIRSTATS mention."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Check welcome message contains dbt Bootcamp, not CEU
        welcome_text = " ".join([m.value for m in at.markdown])
        assert "dbt (Data Build Tool) Bootcamp" in welcome_text
        assert "CEU Modern Data Platforms" not in welcome_text
        # Default welcome now mentions AIRSTATS
        assert "AIRSTATS capstone database" in welcome_text

    def test_ceu_mode_welcome_message(self):
        """CEU mode shows CEU Modern Data Platforms branding."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        # Check for CEU branding
        welcome_text = " ".join([m.value for m in at.markdown])
        assert "CEU Modern Data Platforms" in welcome_text
        assert "AIRSTATS capstone database" in welcome_text

    def test_default_mode_session_state(self):
        """Default mode sets course_mode to 'default'."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        assert at.session_state.course_mode == "default"

    def test_ceu_mode_session_state(self):
        """CEU query param sets course_mode to 'ceu'."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()
        assert at.session_state.course_mode == "ceu"

    def test_ceu_mode_persists_through_steps(self):
        """CEU mode persists when navigating through steps."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        # Navigate to step 1
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.course_mode == "ceu"


class TestModeSelection:
    """Test mode selection behavior."""

    def test_mode_selector_renders_in_default_mode(self):
        """Mode selector renders when not in CEU mode."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        radio = at.radio(key="radio_setup_mode")
        assert radio is not None
        assert radio.value == "Standard Setup"

    def test_no_mode_selector_in_ceu_mode(self):
        """No mode selector when ?course=ceu."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        try:
            at.radio(key="radio_setup_mode")
            pytest.fail("Mode selector should not exist in CEU mode")
        except KeyError:
            pass  # Expected

    def test_switching_modes_resets_step(self):
        """Switching between modes resets step to 0."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Start in standard mode, go to step 1
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step == 1

        # Switch to capstone mode
        at.radio(key="radio_setup_mode").set_value("Set up Capstone").run()
        assert at.session_state.step == 0

    def test_capstone_mode_landing_page(self):
        """Capstone landing page shows warning about pre-Feb-2026 students."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Switch to capstone mode
        at.radio(key="radio_setup_mode").set_value("Set up Capstone").run()

        # Check for capstone-specific content
        all_markdown = " ".join([m.value for m in at.markdown])
        assert "before 20 February 2026" in all_markdown
        assert "AIRSTATS" in all_markdown


class TestStandardSetupSteps:
    """Test the standard setup step navigation (now 3 steps instead of 4)."""

    def test_step_1_has_keypair_expander(self):
        """Step 1 contains keypair generation in an expander, not a separate step."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Go to step 1
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step == 1

        # Keypair should be generated
        assert "keypair" in at.session_state

        # Step 1 header should say "Snowflake Setup", not "Generate Keys"
        all_markdown = " ".join([m.value for m in at.markdown])
        assert "Step 1: Snowflake Setup" in all_markdown

    def test_step_1_is_snowflake_setup_not_keypair(self):
        """Step 1 is now Snowflake setup (credentials form), not keypair generation."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Go to step 1
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step == 1

        # Should have credentials form elements
        assert at.text_input(key="input_snowflake_account") is not None
        assert at.text_input(key="input_snowflake_username") is not None
        assert at.text_input(key="input_snowflake_password") is not None

    def test_no_separate_keypair_step(self):
        """There should be no separate keypair step (no btn_continue_to_snowflake)."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Go to step 1
        at.button(key="btn_start_setup").click().run()

        # The old "Continue to Snowflake Setup" button should NOT exist
        try:
            at.button(key="btn_continue_to_snowflake")
            pytest.fail("btn_continue_to_snowflake should not exist in new flow")
        except KeyError:
            pass  # Expected


class TestSqlSectionParsing:
    """Test SQL section parsing for course modes."""

    def test_capstone_section_exists_in_resources(self):
        """Verify capstone_airstats section exists in capstone-resources.md."""
        import os
        import sys

        # Add parent directory to path to import streamlit_app
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from streamlit_app import get_sql_commands, CURRENT_DIR

        capstone_path = f"{CURRENT_DIR}/capstone-resources.md"
        assert os.path.exists(capstone_path), "capstone-resources.md should exist"

        with open(capstone_path, "r") as f:
            md = f.read()

        commands = get_sql_commands(md)
        assert "capstone_airstats" in commands, "capstone_airstats section should exist"
        assert len(commands["capstone_airstats"]) > 0, "Should have SQL commands"

        # Verify AIRSTATS content
        all_commands = " ".join(commands["capstone_airstats"])
        assert "AIRSTATS" in all_commands
        assert "airports" in all_commands.lower()
        assert "runways" in all_commands.lower()
        assert "airport_comments" in all_commands.lower()

    def test_default_resources_do_not_contain_capstone(self):
        """Verify course-resources.md does not contain capstone section."""
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from streamlit_app import get_sql_commands, CURRENT_DIR

        with open(f"{CURRENT_DIR}/course-resources.md", "r") as f:
            md = f.read()

        commands = get_sql_commands(md)
        assert "capstone_airstats" not in commands, (
            "course-resources.md should not contain capstone_airstats section"
        )


class TestCeuModeFullFlow:
    """Test full CEU mode flow with Snowflake (integration test)."""

    @pytest.mark.ceu
    def test_ceu_complete_setup_flow(self, snowflake_credentials):
        """Test CEU mode creates AIRSTATS database alongside AIRBNB."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        # Verify CEU mode is active
        assert at.session_state.course_mode == "ceu"

        # Navigate through steps
        at.button(key="btn_start_setup").click().run()
        assert at.session_state.step == 1

        # Enter credentials
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

        # Run setup (includes AIRSTATS)
        at.button(key="btn_start_snowflake_setup").click().run(timeout=300)

        # Verify no exceptions
        assert not at.exception, f"Setup raised exception: {at.exception}"

        # Check for errors
        if len(at.error) > 0:
            error_messages = [e.value for e in at.error]
            pytest.fail(f"Setup showed errors: {error_messages}")

        # Verify we reached step 2
        assert at.session_state.step == 2, (
            f"Expected step 2, got step {at.session_state.step}"
        )
