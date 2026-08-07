"""Tests for the credentials form's submission mechanics.

These exist because of a bug AppTest cannot reproduce on its own. A plain
``st.text_input`` only sends its value to the server when it loses focus, and
that commit races the click on a plain ``st.button``: type a password, click
straight through to "Start Setup", and the click's rerun can reach the server
first. The script then sees an empty password and answers "Please provide a
password" while the student is staring at a filled-in field.

AppTest writes widget state directly, so both orderings look identical to it and
no assertion about values can catch a regression here. What can be asserted is
the structure that rules the race out: the credential fields and the submit
button belong to one ``st.form``, which submits them together in a single
message. Take the form away and these tests fail.
"""

import pytest
from streamlit.testing.v1 import AppTest

from tests.conftest import APP_FILE

# Every credential the connection needs must travel with the click, not on its
# own blur. The account field is deliberately not here: it lives outside the form
# so it can validate as soon as focus leaves it.
CREDENTIAL_INPUT_KEYS = [
    "input_snowflake_username",
    "input_snowflake_password",
    "input_totp_passcode",
]


def _at_on_step_1():
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.button(key="btn_start_setup").click().run()
    return at


def _at_on_capstone_step_1():
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.button(key="btn_start_capstone").click().run()
    return at


class TestCredentialsAreSubmittedAtomically:
    @pytest.mark.parametrize("input_key", CREDENTIAL_INPUT_KEYS)
    def test_every_credential_field_is_submitted_with_the_start_button(self, input_key):
        at = _at_on_step_1()

        field = at.text_input(key=f"std_{input_key}")
        submit = at.button(key="btn_start_snowflake_setup")

        assert field.proto.form_id, (
            f"{input_key} is outside a form — its value can be lost when the "
            "student clicks Start Setup without leaving the field first"
        )
        assert field.proto.form_id == submit.proto.form_id

    def test_start_setup_is_a_form_submit_button(self):
        at = _at_on_step_1()

        assert at.button(key="btn_start_snowflake_setup").proto.is_form_submitter

    def test_the_account_field_stays_outside_the_form(self):
        """It validates on blur, and form fields say nothing until submit."""
        at = _at_on_step_1()

        assert not at.text_input(key="std_input_snowflake_account").proto.form_id

    @pytest.mark.parametrize("input_key", CREDENTIAL_INPUT_KEYS)
    def test_the_capstone_form_submits_atomically_too(self, input_key):
        at = _at_on_capstone_step_1()

        field = at.text_input(key=f"cap_{input_key}")
        submit = at.button(key="btn_start_capstone_setup")

        assert field.proto.form_id
        assert field.proto.form_id == submit.proto.form_id

    def test_the_two_tabs_use_separate_forms(self):
        """Both tabs render on every run, so a shared form key would collide."""
        at = _at_on_step_1()
        at.button(key="btn_start_capstone").click().run()

        std_form = at.text_input(key="std_input_snowflake_password").proto.form_id
        cap_form = at.text_input(key="cap_input_snowflake_password").proto.form_id

        assert std_form and cap_form
        assert std_form != cap_form


class TestEmptyPasswordIsStillRejected:
    def test_submitting_without_a_password_asks_for_one(self, monkeypatch):
        monkeypatch.setenv("SNOWFLAKE_PASSWORD", "")
        at = _at_on_step_1()

        at.text_input(key="std_input_snowflake_account").set_value("frgcsyo-ie17820")
        at.button(key="btn_start_snowflake_setup").click().run()

        assert any("provide a password" in e.value for e in at.get("error"))
