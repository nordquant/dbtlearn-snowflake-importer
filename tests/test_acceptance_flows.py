"""Acceptance tests — one per student-facing flow, end to end against real Snowflake.

The existing integration tests (test_full_flow.py) stop at "the app reached the
download screen without showing an error". These go one step further and check
the thing the student actually walks away with: they take the generated
`profiles.yml` / `preset-instructions.md` / `set-env.sh` and authenticate to
Snowflake with them. A bug in the PEM escaping, the account substitution, or the
shell quoting breaks the student's dbt project while every existing test still
passes.

Flow coverage:
  * Default Setup -> profiles.yml            test_standard_setup_flow_*
  * Re-download Preset Instructions (tab 3)  test_preset_recovery_flow_*
  * Download env-var scripts (tab 4)         test_env_scripts_flow_*
  * Skip the automated setup (manual SQL)    test_manual_sql_flow_*
  * Two students in parallel                 test_parallel_sessions_*
Capstone-only and CEU mode are covered in test_full_flow.py.

ORDERING: every test here that provisions Snowflake replaces the `dbt` and
`PRESET` users (the setup SQL is `DROP USER IF EXISTS` + `CREATE USER`), which
invalidates the keys any earlier test was handed. Tests that provision are
therefore self-contained — they verify against Snowflake before returning. Only
the three tests sharing `completed_standard_setup` read shared state, and they
are defined before the provisioning ones.

These hit a real Snowflake account and take several minutes:

    uv run pytest tests/test_acceptance_flows.py -v -s --timeout=1800
"""

import json
import re
import subprocess

import pytest
from sqlalchemy import text
from streamlit.testing.v1 import AppTest

from streamlit_app import (
    STEP_MANUAL_SQL,
    build_manual_sql_script,
    generate_preset_instructions,
    generate_profiles_yml,
    generate_set_env_sh,
    get_dbt_connection,
    get_snowflake_connection,
    parse_profiles_yml,
    parse_profiles_yml_full,
)

# Provisioning imports three tables from S3, so allow the same headroom as
# test_full_flow.py.
SNOWFLAKE_SETUP_TIMEOUT = 300


def _start_standard_setup(credentials):
    """Drive a fresh session from the landing page to step 1 with credentials filled."""
    at = AppTest.from_file("streamlit_app.py", default_timeout=30)
    at.run()
    assert not at.exception, f"App failed to start: {at.exception}"

    at.button(key="btn_start_setup").click().run()
    assert at.session_state.step_standard == 1

    at.text_input(key="std_input_snowflake_account").set_value(credentials["account"])
    at.text_input(key="std_input_snowflake_username").set_value(credentials["username"])
    at.text_input(key="std_input_snowflake_password").set_value(credentials["password"])
    at.run()
    return at


def _run_standard_setup(credentials):
    """Run the whole Default Setup flow and return the session sitting on step 2."""
    at = _start_standard_setup(credentials)

    at.button(key="btn_start_snowflake_setup").click().run(
        timeout=SNOWFLAKE_SETUP_TIMEOUT
    )

    assert not at.exception, f"Setup raised: {at.exception}"
    if at.error:
        pytest.fail(f"Setup showed errors: {[e.value for e in at.error]}")
    assert at.session_state.step_standard == 2, (
        f"Expected the download screen, got step {at.session_state.step_standard}"
    )
    return at


def _profiles_yml_for(at):
    """Build the exact profiles.yml the step-2 download button serves for a session.

    AppTest exposes no download_button accessor, so this mirrors what step 2 does
    with the session's own state rather than clicking through it.
    """
    return generate_profiles_yml(
        at.session_state.snowflake_account,
        at.session_state.keypair.private_key_pem_text,
    )


def _connect_with_pem(account, login_name, role, schema, private_key_pem):
    """Authenticate to Snowflake with a PEM and run a query. Raises on failure."""
    with get_dbt_connection(account, login_name, role, private_key_pem) as conn:
        conn.execute(text(f"USE ROLE {role}"))
        conn.execute(text("USE DATABASE AIRBNB"))
        conn.execute(text(f"USE SCHEMA {schema}"))
        return conn.execute(text("SELECT CURRENT_USER(), CURRENT_ROLE()")).fetchone()


@pytest.fixture(scope="session")
def completed_standard_setup(snowflake_credentials):
    """Provision Snowflake once and hand back what the student downloads."""
    at = _run_standard_setup(snowflake_credentials)
    return {
        "account": at.session_state.snowflake_account,
        "keypair": at.session_state.keypair,
        "profiles_yml": _profiles_yml_for(at),
    }


class TestStandardSetupFlow:
    """Default Setup tab: the profiles.yml a student downloads must actually work."""

    def test_standard_setup_flow_profiles_yml_names_the_typed_account(
        self, completed_standard_setup, snowflake_credentials
    ):
        account, _key = parse_profiles_yml(completed_standard_setup["profiles_yml"])
        assert account == snowflake_credentials["account"], (
            "profiles.yml must carry the account the student typed, not a default "
            "or another session's value"
        )

    def test_standard_setup_flow_profiles_yml_authenticates_as_dbt(
        self, completed_standard_setup
    ):
        """The downloaded profiles.yml is what dbt uses — connect with exactly it."""
        account, escaped_key = parse_profiles_yml(
            completed_standard_setup["profiles_yml"]
        )
        pem = escaped_key.replace("\\n", "\n")

        user, role = _connect_with_pem(account, "dbt", "TRANSFORM", "RAW", pem)

        assert user.upper() == "DBT"
        assert role.upper() == "TRANSFORM"

    def test_standard_setup_flow_dbt_user_can_read_the_imported_data(
        self, completed_standard_setup
    ):
        """The grants are only useful if the raw tables are readable through them."""
        account, escaped_key = parse_profiles_yml(
            completed_standard_setup["profiles_yml"]
        )
        pem = escaped_key.replace("\\n", "\n")

        with get_dbt_connection(account, "dbt", "TRANSFORM", pem) as conn:
            conn.execute(text("USE ROLE TRANSFORM"))
            conn.execute(text("USE DATABASE AIRBNB"))
            conn.execute(text("USE SCHEMA RAW"))
            for table in ("RAW_LISTINGS", "RAW_HOSTS", "RAW_REVIEWS"):
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM RAW.{table}")
                ).fetchone()[0]
                assert count > 0, f"{table} is empty after import"


class TestPresetRecoveryFlow:
    """Tab 3: upload profiles.yml, get preset-instructions.md back."""

    def test_preset_recovery_flow_regenerates_the_original_instructions(
        self, completed_standard_setup
    ):
        account, escaped_key = parse_profiles_yml(
            completed_standard_setup["profiles_yml"]
        )
        recovered = generate_preset_instructions(account, escaped_key)

        expected = generate_preset_instructions(
            completed_standard_setup["account"],
            completed_standard_setup["keypair"].private_key_pem_text,
        )
        assert recovered == expected, (
            "Recovery must reproduce the file the student originally downloaded"
        )

    def test_preset_recovery_flow_key_authenticates_as_preset(
        self, completed_standard_setup
    ):
        """The key embedded in the recovered markdown must work for the REPORTER role."""
        account, escaped_key = parse_profiles_yml(
            completed_standard_setup["profiles_yml"]
        )
        recovered = generate_preset_instructions(account, escaped_key)

        security_json = json.loads(
            re.search(r"```json\n(.*?)\n```", recovered, re.S).group(1)
        )
        pem = security_json["auth_params"]["privatekey_body"].replace("\\n", "\n")
        assert security_json["auth_params"]["privatekey_pass"] == "q"

        user, role = _connect_with_pem(account, "preset", "REPORTER", "DEV", pem)

        assert user.upper() == "PRESET"
        assert role.upper() == "REPORTER"


class TestEnvScriptsFlow:
    """Tab 4: upload profiles.yml, get a shell script that exports the credentials."""

    def test_env_scripts_flow_key_survives_a_real_bash_source(
        self, completed_standard_setup, tmp_path
    ):
        """Source the generated script in a real shell and use what comes back out.

        A Python-side string check would not catch quoting bugs that mangle the
        PEM's newlines once bash gets hold of it.
        """
        values = parse_profiles_yml_full(completed_standard_setup["profiles_yml"])
        script = tmp_path / "set-env.sh"
        script.write_text(generate_set_env_sh(values))

        result = subprocess.run(
            ["bash", "-c", f'. "{script}" && printf "%s\\n%s\\n%s" '
             '"$SNOWFLAKE_ACCOUNT" "$DBT_USER" "$PRIVATE_KEY"'],
            capture_output=True,
            text=True,
            check=True,
        )
        account, dbt_user, pem = result.stdout.split("\n", 2)

        assert account == completed_standard_setup["account"]
        assert dbt_user == "dbt"
        assert pem.startswith("-----BEGIN ENCRYPTED PRIVATE KEY-----")

        user, role = _connect_with_pem(account, dbt_user, "TRANSFORM", "RAW", pem)

        assert user.upper() == "DBT"
        assert role.upper() == "TRANSFORM"


class TestManualSqlFlow:
    """Skip the automated setup: the pasteable script must provision a working account.

    This is the only path open to students whose Snowflake account has a passkey
    enrolled, so a broken script leaves them with nowhere to go. Provisions
    Snowflake — see the ORDERING note at the top of the file.
    """

    def test_manual_sql_flow_script_provisions_a_working_dbt_user(
        self, snowflake_credentials
    ):
        at = _start_standard_setup(snowflake_credentials)
        at.button(key="btn_show_manual_sql").click().run()
        assert at.session_state.step_standard == STEP_MANUAL_SQL

        keypair = at.session_state.keypair
        script = build_manual_sql_script(keypair.public_key)
        assert keypair.public_key in script, "The session's public key must be baked in"

        # A Snowflake worksheet splits the pasted script on semicolons; do the same.
        statements = [s.strip() for s in script.split(";") if s.strip()]
        with get_snowflake_connection(
            snowflake_credentials["account"],
            snowflake_credentials["username"],
            snowflake_credentials["password"],
        ) as conn:
            for statement in statements:
                conn.execute(text(statement))
                conn.commit()

        # Back in the app: confirm the account, land on the download screen.
        at.text_input(key="manual_input_snowflake_account").set_value(
            snowflake_credentials["account"]
        )
        at.run()
        at.button(key="btn_manual_done").click().run()
        assert at.session_state.step_standard == 2, (
            f"Expected the download screen, got step {at.session_state.step_standard}"
        )

        account, escaped_key = parse_profiles_yml(_profiles_yml_for(at))
        user, role = _connect_with_pem(
            account, "dbt", "TRANSFORM", "RAW", escaped_key.replace("\\n", "\n")
        )

        assert user.upper() == "DBT"
        assert role.upper() == "TRANSFORM"


class TestParallelSessions:
    """Two students on one container must not be handed the same credentials.

    Provisions Snowflake twice — see the ORDERING note at the top of the file.
    """

    def test_parallel_sessions_get_isolated_credentials(self, snowflake_credentials):
        """Regression guard for the shared-keypair bug.

        `generate_keys` was once wrapped in @st.cache_data, whose cache is
        process-global and was keyed on a constant argument, so every student on
        a container received one private key. The give-away is the final
        assertion: the first session's profiles.yml keeps working after the
        second session re-keys the `dbt` user only if both were handed the same
        key.

        Both sessions target the same Snowflake account because there is one test
        account; real students each have their own, which is why the second
        setup legitimately supersedes the first here.
        """
        first = _run_standard_setup(snowflake_credentials)
        first_profiles = _profiles_yml_for(first)
        first_pem = parse_profiles_yml(first_profiles)[1].replace("\\n", "\n")

        second = _run_standard_setup(snowflake_credentials)
        second_profiles = _profiles_yml_for(second)
        second_pem = parse_profiles_yml(second_profiles)[1].replace("\\n", "\n")

        assert first.session_state.keypair.public_key != (
            second.session_state.keypair.public_key
        ), "Two sessions were handed the same keypair"
        assert first_profiles != second_profiles

        # The second session provisioned last, so its key is the registered one.
        user, _role = _connect_with_pem(
            snowflake_credentials["account"], "dbt", "TRANSFORM", "RAW", second_pem
        )
        assert user.upper() == "DBT"

        # And the first session's key must now be rejected. If the two sessions
        # shared a key this would still succeed.
        with pytest.raises(Exception) as excinfo:
            _connect_with_pem(
                snowflake_credentials["account"], "dbt", "TRANSFORM", "RAW", first_pem
            )
        assert "JWT" in str(excinfo.value) or "authenticat" in str(excinfo.value).lower()
