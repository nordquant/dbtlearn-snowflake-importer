"""Tests for the two ways a bad account identifier is caught before it confuses a student.

Both exist because of the same production incident. The account field defaults to
``ACCOUNT_PLACEHOLDER``, and the placeholder happens to satisfy the identifier
format check, so a student who filled in only a password reached a real login
attempt against ``xxxxxx-xxxxxxxx.snowflakecomputing.com``. Snowflake 404s it
(error 290404), the app showed a generic "Error connecting to Snowflake" with a
raw stacktrace, and a Slack alert fired naming an account nobody ever typed.

So: the placeholder never leaves the form, and a 404 that does happen is reported
as the typo it is, with the offending identifier spelled out — and quietly, since
a mistyped account says nothing about the health of the server.
"""

import logging

import pytest
from streamlit.testing.v1 import AppTest

import streamlit_app
from streamlit_app import (
    ACCOUNT_PLACEHOLDER,
    _handle_account_not_found,
    _is_account_not_found,
    account_is_entered,
)
from tests.conftest import APP_FILE

# Verbatim from the Slack alert that prompted this work, account and username as
# they arrived — both are the untouched defaults.
PRODUCTION_404 = (
    "290404 (08001): None: 404 Not Found: post "
    "xxxxxx-xxxxxxxx.snowflakecomputing.com:443/session/v1/login-request"
)


def _at_on_step_1(monkeypatch):
    """A fresh session on the credentials screen with no account pre-filled.

    SNOWFLAKE_ACCOUNT is cleared because .env sets it for the integration tests,
    and a pre-filled field is exactly what these tests must not have.
    """
    monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
    at = AppTest.from_file(APP_FILE, default_timeout=30)
    at.run()
    at.button(key="btn_start_setup").click().run()
    return at


def _errors(at):
    return [e.value for e in at.get("error")]


class TestAccountIsEntered:
    @pytest.mark.parametrize("raw", ["", "   ", ACCOUNT_PLACEHOLDER, f"  {ACCOUNT_PLACEHOLDER}  "])
    def test_untouched_field_does_not_count_as_entered(self, raw):
        assert not account_is_entered(raw)

    @pytest.mark.parametrize("raw", ["frgcsyo-ie17820", "frgcsyo-ie17820.aws", "xxxxxx-ie17820"])
    def test_a_real_identifier_counts_as_entered(self, raw):
        assert account_is_entered(raw)


class TestPlaceholderNeverReachesSnowflake:
    def test_submitting_the_untouched_placeholder_asks_the_student_to_fill_it_in(self, monkeypatch):
        at = _at_on_step_1(monkeypatch)
        at.text_input(key="std_input_snowflake_password").set_value("hunter2")

        at.button(key="btn_start_snowflake_setup").click().run()

        assert any(ACCOUNT_PLACEHOLDER in e for e in _errors(at)), (
            f"Expected the placeholder to be named in an error, got: {_errors(at)}"
        )
        # Still on the credentials screen: no connection was attempted.
        assert at.session_state.step_standard == 1

    def test_a_malformed_account_is_rejected_before_connecting(self, monkeypatch):
        at = _at_on_step_1(monkeypatch)
        at.text_input(key="std_input_snowflake_account").set_value("my account!")
        at.text_input(key="std_input_snowflake_password").set_value("hunter2")

        at.button(key="btn_start_snowflake_setup").click().run()

        assert any("doesn't look like a Snowflake account" in e for e in _errors(at))
        assert at.session_state.step_standard == 1

    def test_the_capstone_tab_is_guarded_too(self, monkeypatch):
        monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.run()
        at.button(key="btn_start_capstone").click().run()
        at.text_input(key="cap_input_snowflake_password").set_value("hunter2")

        at.button(key="btn_start_capstone_setup").click().run()

        assert any(ACCOUNT_PLACEHOLDER in e for e in _errors(at))
        assert at.session_state.step_capstone == 1


class TestAccountNotFoundDetection:
    def test_the_production_error_is_recognised(self):
        assert _is_account_not_found(Exception(PRODUCTION_404))

    def test_it_reads_through_the_sqlalchemy_wrapper(self):
        """SQLAlchemy wraps the driver error; the code only lives on ``orig``."""

        class Wrapped(Exception):
            orig = Exception(PRODUCTION_404)

        assert _is_account_not_found(Wrapped("(snowflake.connector.errors.DatabaseError)"))

    @pytest.mark.parametrize(
        "message",
        [
            "250001 (08001): Failed to connect to DB: Incorrect username or password was specified.",
            "Multi-factor authentication is required",
            "404 Not Found",  # a 404 from anywhere else is not an account problem
        ],
    )
    def test_other_failures_are_left_alone(self, message):
        assert not _is_account_not_found(Exception(message))


class TestAccountNotFoundMessage:
    """The message must name the identifier — the student's own typo is the fix."""

    def _capture(self, monkeypatch):
        """Capture what the student is shown, with Slack fully armed.

        The webhook is *set* on purpose: the alerting tests below have to prove the
        404 path stays quiet by choice, not because the webhook happened to be absent.
        """
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/T000/B000/xxx")
        shown = []
        monkeypatch.setattr(streamlit_app.st, "error", shown.append)
        return shown

    def test_it_spells_out_the_account_that_failed(self, monkeypatch, caplog):
        shown = self._capture(monkeypatch)

        with caplog.at_level(logging.WARNING):
            result = _handle_account_not_found(
                "sess-1", "frgcsyo-ie1782O", "admin", Exception(PRODUCTION_404)
            )

        assert result is None
        assert len(shown) == 1
        assert "frgcsyo-ie1782O" in shown[0]
        assert "frgcsyo-ie1782O" in caplog.text

    def test_it_does_not_send_the_student_to_the_fallback_app(self, monkeypatch):
        """The fallback app would 404 on the same identifier — a round trip to nowhere."""
        shown = self._capture(monkeypatch)

        _handle_account_not_found(
            "sess-1", "frgcsyo-ie1782O", "admin", Exception(PRODUCTION_404)
        )

        assert streamlit_app.FALLBACK_APP_URL not in shown[0]


class TestA404NeverAlerts:
    """A mistyped account is the student's problem to fix, not an incident.

    Alerting on it is what buried the signal in the first place: the alerts that
    matter are the ones where Snowflake refuses *our server*, and they are
    indistinguishable from typos once both land in the same channel.
    """

    def _arm_slack(self, monkeypatch):
        posts = []
        monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://hooks.slack.example/T000/B000/xxx")
        monkeypatch.setattr(streamlit_app.st, "error", lambda *a, **k: None)
        monkeypatch.setattr(
            streamlit_app.requests, "post", lambda *a, **k: posts.append((a, k))
        )
        return posts

    def test_the_404_handler_posts_nothing(self, monkeypatch):
        posts = self._arm_slack(monkeypatch)

        _handle_account_not_found(
            "sess-1", "frgcsyo-ie1782O", "admin", Exception(PRODUCTION_404)
        )

        assert posts == [], f"A mistyped account paged Slack: {posts}"

    def test_other_connection_failures_still_alert(self, monkeypatch):
        """The guard above must not have disarmed alerting altogether.

        _notify_slack_of_connection_error only fires for requests served from
        PRIMARY_HOST, and bare-mode tests have no request host at all — so
        PRIMARY_HOST is pointed at the empty string the host check falls back to.
        That satisfies the gate without pretending to be a real Streamlit request.
        """
        posts = self._arm_slack(monkeypatch)
        monkeypatch.setattr(streamlit_app, "PRIMARY_HOST", "")

        streamlit_app._notify_slack_of_connection_error(
            "sess-1", "DBAPIError", "frgcsyo-ie17820", "admin", Exception("boom")
        )

        assert len(posts) == 1, "Non-404 failures must still page Slack"
        assert "boom" in posts[0][1]["json"]["text"]
