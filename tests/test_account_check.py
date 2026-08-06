"""Tests for the "Check account identifier" button.

Snowflake redirects to the login console for accounts that exist and 404s for
ones that don't, which lets us validate an identifier without credentials.
"""

import pytest
import requests
from streamlit.testing.v1 import AppTest

from tests.conftest import APP_FILE

from streamlit_app import check_snowflake_account_exists


class _FakeResponse:
    def __init__(self, status_code):
        self.status_code = status_code


class TestCheckSnowflakeAccountExists:
    def _patch_get(self, monkeypatch, result):
        calls = {}

        def fake_get(url, **kwargs):
            calls["url"] = url
            calls["kwargs"] = kwargs
            if isinstance(result, Exception):
                raise result
            return _FakeResponse(result)

        monkeypatch.setattr(requests, "get", fake_get)
        return calls

    def test_redirect_to_console_means_the_account_exists(self, monkeypatch):
        self._patch_get(monkeypatch, 302)

        exists, _ = check_snowflake_account_exists("frgcsyo-ie17820")

        assert exists is True

    def test_404_means_the_account_does_not_exist(self, monkeypatch):
        self._patch_get(monkeypatch, 404)

        exists, detail = check_snowflake_account_exists("nosuchacct-zz99999")

        assert exists is False
        assert "404" in detail

    def test_network_failure_is_unknown_not_invalid(self, monkeypatch):
        """A blocked outbound request must never be shown as a bad account."""
        self._patch_get(monkeypatch, requests.ConnectionError("no route to host"))

        exists, detail = check_snowflake_account_exists("frgcsyo-ie17820")

        assert exists is None
        assert "no route to host" in detail

    def test_unexpected_server_error_is_unknown(self, monkeypatch):
        self._patch_get(monkeypatch, 503)

        exists, _ = check_snowflake_account_exists("frgcsyo-ie17820")

        assert exists is None

    def test_queries_the_account_url_without_following_redirects(self, monkeypatch):
        calls = self._patch_get(monkeypatch, 302)

        check_snowflake_account_exists("frgcsyo-ie17820")

        assert calls["url"] == "https://frgcsyo-ie17820.snowflakecomputing.com/"
        assert calls["kwargs"]["allow_redirects"] is False
        assert calls["kwargs"]["timeout"] > 0


class TestAccountCheckUI:
    @pytest.fixture(autouse=True)
    def _no_prefilled_account(self, monkeypatch):
        monkeypatch.delenv("SNOWFLAKE_ACCOUNT", raising=False)

    def _at_on_step_1(self, monkeypatch, status):
        monkeypatch.setattr(
            requests,
            "get",
            lambda url, **kwargs: _FakeResponse(status),
        )
        at = AppTest.from_file(APP_FILE, default_timeout=30)
        at.run()
        at.button(key="btn_start_setup").click().run()
        return at

    def test_button_stays_clickable_so_typing_then_clicking_works(self, monkeypatch):
        """Clicking is what commits a freshly typed value — disabling it would trap users."""
        at = self._at_on_step_1(monkeypatch, 302)

        assert not at.button(key="std_input_snowflake_account_check_button").disabled

    def test_clicking_without_an_account_asks_for_one(self, monkeypatch):
        at = self._at_on_step_1(monkeypatch, 302)

        at.button(key="std_input_snowflake_account_check_button").click().run()

        assert not at.exception, at.exception
        assert any(
            "Enter your Snowflake account first" in w.value for w in at.get("warning")
        )

    def test_typing_and_clicking_in_one_go_checks_the_typed_value(self, monkeypatch):
        """The value need not be committed with Enter first."""
        at = self._at_on_step_1(monkeypatch, 302)

        at.text_input(key="std_input_snowflake_account").set_value("frgcsyo-ie17820")
        at.button(key="std_input_snowflake_account_check_button").click().run()

        assert any("valid Snowflake account" in s.value for s in at.get("success"))

    def test_valid_account_reports_success(self, monkeypatch):
        at = self._at_on_step_1(monkeypatch, 302)

        at.text_input(key="std_input_snowflake_account").set_value(
            "frgcsyo-ie17820"
        ).run()
        at.button(key="std_input_snowflake_account_check_button").click().run()

        assert not at.exception, at.exception
        assert any("valid Snowflake account" in s.value for s in at.get("success"))

    def test_unknown_account_reports_an_error(self, monkeypatch):
        at = self._at_on_step_1(monkeypatch, 404)

        at.text_input(key="std_input_snowflake_account").set_value(
            "nosuchacct-zz99999"
        ).run()
        at.button(key="std_input_snowflake_account_check_button").click().run()

        assert any("doesn't know an account" in e.value for e in at.get("error"))

    def test_result_disappears_when_the_account_is_edited(self, monkeypatch):
        """A stale verdict on a since-changed identifier would be misleading."""
        at = self._at_on_step_1(monkeypatch, 404)

        at.text_input(key="std_input_snowflake_account").set_value(
            "nosuchacct-zz99999"
        ).run()
        at.button(key="std_input_snowflake_account_check_button").click().run()
        assert len(at.get("error")) == 1

        at.text_input(key="std_input_snowflake_account").set_value(
            "frgcsyo-ie17820"
        ).run()

        assert not any("doesn't know an account" in e.value for e in at.get("error"))

    def test_check_is_available_on_the_manual_page_too(self, monkeypatch):
        at = self._at_on_step_1(monkeypatch, 302)
        at.button(key="btn_show_manual_sql").click().run()

        at.text_input(key="manual_input_snowflake_account").set_value(
            "frgcsyo-ie17820"
        ).run()
        at.button(key="manual_input_snowflake_account_check_button").click().run()

        assert not at.exception, at.exception
        assert any("valid Snowflake account" in s.value for s in at.get("success"))
