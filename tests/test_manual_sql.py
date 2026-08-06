"""Tests for the manual-SQL flow (skipping the automated Snowflake setup).

Students whose Snowflake account only has a passkey enrolled cannot authenticate
programmatically at all, so they need the SQL handed to them to run themselves.
"""

import os

import pytest
from streamlit.testing.v1 import AppTest

from streamlit_app import (
    CURRENT_DIR,
    SNOWFLAKE_PASTE_VIDEO,
    STEP_MANUAL_SQL,
    build_manual_sql_script,
    get_raw_sql_blocks,
    load_manual_sql_blocks,
)

PUBLIC_KEY_PLACEHOLDER = "<<Add Your Public Key File's content here>>"


class TestGetRawSqlBlocks:
    """The raw extractor keeps blocks pasteable, unlike get_sql_commands()."""

    def test_preserves_comments_and_blank_lines(self):
        md = (
            "# Heading\n"
            "```sql {#demo}\n"
            "-- A comment\n"
            "SELECT 1;\n"
            "\n"
            "SELECT 2;\n"
            "```\n"
        )
        blocks = get_raw_sql_blocks(md)

        assert list(blocks.keys()) == ["demo"]
        assert blocks["demo"] == "-- A comment\nSELECT 1;\n\nSELECT 2;"

    def test_substitutes_public_key(self):
        md = f'```sql {{#demo}}\nRSA_PUBLIC_KEY="{PUBLIC_KEY_PLACEHOLDER}"\n```\n'

        blocks = get_raw_sql_blocks(md, "MYKEY")

        assert blocks["demo"] == 'RSA_PUBLIC_KEY="MYKEY"'

    def test_leaves_placeholder_when_no_key_given(self):
        md = f'```sql {{#demo}}\nRSA_PUBLIC_KEY="{PUBLIC_KEY_PLACEHOLDER}"\n```\n'

        assert PUBLIC_KEY_PLACEHOLDER in get_raw_sql_blocks(md)["demo"]

    def test_ignores_unnamed_sql_blocks(self):
        md = "```sql\nSELECT 'not mine';\n```\n```sql {#demo}\nSELECT 1;\n```\n"

        assert list(get_raw_sql_blocks(md).keys()) == ["demo"]


class TestLoadManualSqlBlocks:
    """The manual page must offer every section the automated setup runs."""

    def test_loads_all_sections_in_execution_order(self):
        blocks = load_manual_sql_blocks("MYKEY")

        assert list(blocks.keys()) == [
            "snowflake_import",
            "snowflake_setup",
            "capstone_airstats",
        ]

    def test_public_key_is_filled_in_everywhere(self):
        blocks = load_manual_sql_blocks("MYKEY")
        joined = "\n".join(blocks.values())

        assert PUBLIC_KEY_PLACEHOLDER not in joined
        assert 'RSA_PUBLIC_KEY="MYKEY"' in joined


class TestBuildManualSqlScript:
    """Every section is combined into one pasteable script."""

    def test_contains_every_section_in_order(self):
        script = build_manual_sql_script("MYKEY")

        positions = [
            script.index("Step 1: Importing Raw Tables"),
            script.index("Step 2: Setting up the dbt User and Roles"),
            script.index("Step 3: Importing AIRSTATS Capstone Tables"),
        ]
        assert positions == sorted(positions)

    def test_section_headers_are_sql_comments(self):
        """The script is executed as a whole, so headers must not break the SQL."""
        script = build_manual_sql_script("MYKEY")

        for line in script.split("\n"):
            if "Step 1: " in line or "Step 2: " in line or "Step 3: " in line:
                assert line.startswith("--"), f"header is not a comment: {line}"

    def test_carries_the_public_key_and_no_placeholder(self):
        script = build_manual_sql_script("MYKEY")

        assert 'RSA_PUBLIC_KEY="MYKEY"' in script
        assert PUBLIC_KEY_PLACEHOLDER not in script

    def test_sections_are_separated_by_a_statement_terminator(self):
        """Blocks are concatenated, so each must end with `;` to stay executable."""
        blocks = load_manual_sql_blocks("MYKEY")

        for section, sql in blocks.items():
            assert sql.rstrip().endswith(";"), f"{section} does not end with ';'"


class TestManualSqlUI:
    """Walk the skip-the-automation path through to the download page."""

    @pytest.fixture(autouse=True)
    def _no_prefilled_account(self, monkeypatch):
        """Ignore a locally configured .env account so the field starts as a placeholder."""
        monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)

    def _at_on_manual_page(self):
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()
        at.button(key="btn_show_manual_sql").click().run()
        return at

    def test_totp_field_is_shown_by_default_and_starts_empty(self):
        """No checkbox to tick — the field is always there, empty means "don't use it"."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()

        assert at.text_input(key="std_input_totp_passcode").value in ("", None)

    def test_skip_button_leads_to_manual_page_with_one_filled_in_sql_field(self):
        at = self._at_on_manual_page()

        assert not at.exception, at.exception
        assert at.session_state.step_standard == STEP_MANUAL_SQL

        code_blocks = [c.value for c in at.get("code")]
        assert len(code_blocks) == 1, (
            f"expected a single combined SQL field, got {len(code_blocks)}"
        )

        sql = code_blocks[0]
        assert PUBLIC_KEY_PLACEHOLDER not in sql
        assert at.session_state.keypair.public_key in sql
        # All three sections are in the one field.
        assert "CREATE OR REPLACE TABLE raw_listings" in sql
        assert "CREATE ROLE TRANSFORM" in sql
        assert "CREATE DATABASE IF NOT EXISTS AIRSTATS" in sql
        # Comments survive so the SQL is readable in a worksheet.
        assert "-- Use an admin role" in sql

    def test_cannot_continue_without_a_valid_account(self):
        """profiles.yml needs the account, so the untouched placeholder must be rejected."""
        at = self._at_on_manual_page()

        at.button(key="btn_manual_done").click().run()

        assert at.session_state.step_standard == STEP_MANUAL_SQL
        assert len(at.error) == 1
        assert "valid Snowflake account" in at.error[0].value

    def test_continue_leads_to_the_download_page(self):
        at = self._at_on_manual_page()

        at.text_input(key="manual_input_snowflake_account").set_value(
            "frgcsyo-ie17820"
        ).run()
        at.button(key="btn_manual_done").click().run()

        assert not at.exception, at.exception
        assert at.session_state.step_standard == 2
        assert at.session_state.snowflake_account == "frgcsyo-ie17820"
        # profiles.yml + preset-instructions.md
        assert len(at.get("download_button")) == 2

    def test_account_is_extracted_from_a_pasted_url(self):
        at = self._at_on_manual_page()

        at.text_input(key="manual_input_snowflake_account").set_value(
            "https://frgcsyo-ie17820.snowflakecomputing.com/console/login"
        ).run()
        at.button(key="btn_manual_done").click().run()

        assert at.session_state.snowflake_account == "frgcsyo-ie17820"

    def test_account_from_step_1_is_carried_over(self):
        """Whatever was typed on the credentials form prefills the manual page."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()

        at.text_input(key="std_input_snowflake_account").set_value(
            "frgcsyo-ie17820"
        ).run()
        at.button(key="btn_show_manual_sql").click().run()

        assert at.text_input(key="manual_input_snowflake_account").value == (
            "frgcsyo-ie17820"
        )
        # ...and it is good enough to continue with straight away.
        at.button(key="btn_manual_done").click().run()
        assert at.session_state.step_standard == 2

    def test_url_pasted_in_step_1_is_carried_over_extracted(self):
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()

        at.text_input(key="std_input_snowflake_account").set_value(
            "https://frgcsyo-ie17820.snowflakecomputing.com/console/login"
        ).run()
        at.button(key="btn_show_manual_sql").click().run()

        assert at.text_input(key="manual_input_snowflake_account").value == (
            "frgcsyo-ie17820"
        )

    def test_back_button_returns_to_the_automated_setup(self):
        at = self._at_on_manual_page()

        at.button(key="btn_manual_back").click().run()

        assert at.session_state.step_standard == 1

    def test_steps_are_numbered_and_in_order(self):
        """The three steps must be impossible to miss or mix up."""
        at = self._at_on_manual_page()

        headings = [
            s.value for s in at.get("subheader") if s.value.strip().startswith(("1)", "2)", "3)"))
        ]
        assert headings == [
            "1) Add your Snowflake Account",
            "2) Copy this Snowflake Command and Paste / Execute in Snowflake",
            "3) Download your dbt config files",
        ]

    def test_walkthrough_video_loops_silently(self):
        """It replaced a GIF, so it has to behave like one: autoplay, loop, no sound."""
        at = self._at_on_manual_page()

        videos = at.get("video")
        assert len(videos) == 1, f"expected one video, got {len(videos)}"

        video = videos[0].proto
        assert video.loop
        assert video.autoplay
        assert video.muted

    def test_walkthrough_video_exists_on_disk(self):
        """The <img> points at Streamlit's static folder, so the file must ship with it."""
        video_path = os.path.join(CURRENT_DIR, "static", SNOWFLAKE_PASTE_VIDEO)

        assert os.path.exists(video_path), f"missing static asset: {video_path}"

    def test_missing_video_does_not_break_the_page(self, monkeypatch):
        monkeypatch.setattr("streamlit_app.SNOWFLAKE_PASTE_VIDEO", "does-not-exist.mp4")

        at = self._at_on_manual_page()

        assert not at.exception, at.exception
        assert len(at.get("code")) == 1


class TestKeypairIsUnobtrusive:
    """Students shouldn't have to think about keypairs at all."""

    def _at_on_step_1(self):
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()
        return at

    def test_keypair_is_generated_without_announcing_it(self):
        at = self._at_on_step_1()

        assert "keypair" in at.session_state
        page_text = " ".join(m.value for m in at.get("markdown"))
        assert "Generating keypair" not in page_text
        assert "Private Key (rsa_key.p8) generated" not in page_text

    def test_downloads_stay_available_behind_the_expander(self):
        at = self._at_on_step_1()

        download_keys = [b.proto.id for b in at.get("download_button")]
        assert any("btn_download_private_key" in k for k in download_keys)
        assert any("btn_download_public_key" in k for k in download_keys)
