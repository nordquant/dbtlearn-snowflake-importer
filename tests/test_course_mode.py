import pytest
from streamlit.testing.v1 import AppTest


class TestCourseModeDetection:
    """Test course mode detection from query parameters."""

    def test_default_mode_welcome_message(self):
        """Default mode shows standard dbt Bootcamp welcome."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Check welcome message contains dbt Bootcamp, not CEU
        welcome_text = " ".join([m.value for m in at.markdown])
        assert "dbt (Data Build Tool) Bootcamp" in welcome_text
        assert "CEU Modern Data Platforms" not in welcome_text

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

        # Navigate to step 2
        at.button(key="btn_continue_to_snowflake").click().run()
        assert at.session_state.course_mode == "ceu"


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

        at.button(key="btn_continue_to_snowflake").click().run()
        assert at.session_state.step == 2

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

        # Verify we reached step 3
        assert at.session_state.step == 3, (
            f"Expected step 3, got step {at.session_state.step}"
        )
