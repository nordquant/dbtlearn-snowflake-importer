"""Tests for the 'Download env scripts' tab and its helpers."""

import pytest
from streamlit.testing.v1 import AppTest

from core.keys import generate_keys
from streamlit_app import (
    generate_profiles_yml,
    generate_set_env_ps1,
    generate_set_env_sh,
    parse_profiles_yml_full,
)


# ===========================================================================
# Unit tests for parse_profiles_yml_full()
# ===========================================================================


class TestParseProfilesYmlFull:
    """Unit tests for parse_profiles_yml_full()."""

    def test_parse_returns_all_fields(self):
        """All four expected fields are present and correct."""
        keypair = generate_keys("q")
        account = "test-org-abc12345"
        profiles = generate_profiles_yml(account, keypair.private_key_pem_text)

        values = parse_profiles_yml_full(profiles)

        assert values["account"] == account
        assert values["user"] == "dbt"
        assert values["private_key_passphrase"] == "q"
        assert "BEGIN ENCRYPTED PRIVATE KEY" in values["private_key"]

    def test_parse_real_newlines_in_key(self):
        """Unlike parse_profiles_yml(), this parser keeps real newlines."""
        keypair = generate_keys("q")
        profiles = generate_profiles_yml("acct-123", keypair.private_key_pem_text)

        values = parse_profiles_yml_full(profiles)

        assert "\n" in values["private_key"]
        assert "\\n" not in values["private_key"]

    def test_parse_defaults_user_and_passphrase(self):
        """Missing user / private_key_passphrase fall back to dbt / q."""
        yaml_content = """\
airbnb:
  outputs:
    dev:
      type: snowflake
      account: myorg-12345
      private_key: "-----BEGIN KEY-----\\nABC\\n-----END KEY-----\\n"
"""
        values = parse_profiles_yml_full(yaml_content)

        assert values["user"] == "dbt"
        assert values["private_key_passphrase"] == "q"

    def test_parse_invalid_yaml(self):
        """Garbage input raises ValueError."""
        with pytest.raises(ValueError, match="Invalid YAML format"):
            parse_profiles_yml_full(":::not valid yaml:::\n  - ][")

    def test_parse_wrong_structure(self):
        """Valid YAML without airbnb.outputs.dev raises ValueError."""
        with pytest.raises(ValueError, match="Invalid profiles.yml structure"):
            parse_profiles_yml_full("foo:\n  bar: baz\n")

    def test_parse_missing_account(self):
        """YAML with dev config but no account raises ValueError."""
        yaml_content = """\
airbnb:
  outputs:
    dev:
      type: snowflake
      user: dbt
      private_key: "some-key"
"""
        with pytest.raises(ValueError, match="Missing 'account'"):
            parse_profiles_yml_full(yaml_content)

    def test_parse_missing_private_key(self):
        """YAML with dev config but no private_key raises ValueError."""
        yaml_content = """\
airbnb:
  outputs:
    dev:
      type: snowflake
      account: myorg-12345
      user: dbt
"""
        with pytest.raises(ValueError, match="Missing 'private_key'"):
            parse_profiles_yml_full(yaml_content)

    def test_parse_dev_and_prod_profile_extracts_dev(self):
        """A profiles.yml with both dev and prod targets returns dev's values."""
        yaml_content = """\
airbnb:
  outputs:
    dev:
      type: snowflake
      account: dev-account-abc12345
      user: dbt
      role: TRANSFORM
      private_key: "-----BEGIN ENCRYPTED PRIVATE KEY-----\\nDEVKEY\\n-----END ENCRYPTED PRIVATE KEY-----\\n"
      private_key_passphrase: q
      database: AIRBNB
      schema: DEV
      threads: 4
      warehouse: COMPUTE_WH
    prod:
      type: snowflake
      account: prod-account-xyz99999
      user: dbt_prod
      role: TRANSFORM
      private_key: "-----BEGIN ENCRYPTED PRIVATE KEY-----\\nPRODKEY\\n-----END ENCRYPTED PRIVATE KEY-----\\n"
      private_key_passphrase: prodpass
      database: AIRBNB
      schema: PROD
      threads: 4
      warehouse: COMPUTE_WH
  target: dev
"""
        values = parse_profiles_yml_full(yaml_content)

        assert values["account"] == "dev-account-abc12345"
        assert values["user"] == "dbt"
        assert values["private_key_passphrase"] == "q"
        assert "DEVKEY" in values["private_key"]
        assert "PRODKEY" not in values["private_key"]


# ===========================================================================
# Unit tests for generate_set_env_sh()
# ===========================================================================


class TestGenerateSetEnvSh:
    """Unit tests for the bash script generator."""

    def _values(self):
        keypair = generate_keys("q")
        return {
            "account": "myorg-12345",
            "user": "dbt",
            "private_key": keypair.private_key,
            "private_key_passphrase": "q",
        }

    def test_contains_all_exports(self):
        out = generate_set_env_sh(self._values())
        assert "export SNOWFLAKE_ACCOUNT=" in out
        assert "export DBT_USER=" in out
        assert "export PRIVATE_KEY=" in out
        assert "export PRIVATE_KEY_PASSPHRASE=" in out

    def test_pem_has_real_newlines(self):
        out = generate_set_env_sh(self._values())
        assert "-----BEGIN ENCRYPTED PRIVATE KEY-----" in out
        assert "-----END ENCRYPTED PRIVATE KEY-----" in out
        # Multi-line PEM means many real newlines in the output.
        assert out.count("\n") > 5

    def test_round_trip(self):
        keypair = generate_keys("q")
        account = "roundtrip-acct-9"
        profiles = generate_profiles_yml(account, keypair.private_key_pem_text)

        values = parse_profiles_yml_full(profiles)
        out = generate_set_env_sh(values)

        assert f'export SNOWFLAKE_ACCOUNT="{account}"' in out


# ===========================================================================
# Unit tests for generate_set_env_ps1()
# ===========================================================================


class TestGenerateSetEnvPs1:
    """Unit tests for the PowerShell script generator."""

    def _values(self):
        keypair = generate_keys("q")
        return {
            "account": "myorg-12345",
            "user": "dbt",
            "private_key": keypair.private_key,
            "private_key_passphrase": "q",
        }

    def test_contains_all_env_assignments(self):
        out = generate_set_env_ps1(self._values())
        assert "$env:SNOWFLAKE_ACCOUNT =" in out
        assert "$env:DBT_USER =" in out
        assert "$env:PRIVATE_KEY =" in out
        assert "$env:PRIVATE_KEY_PASSPHRASE =" in out

    def test_pem_uses_here_string(self):
        out = generate_set_env_ps1(self._values())
        # Opening @" must appear, and closing "@ must sit at column 0.
        assert '@"\n' in out
        assert '\n"@\n' in out
        assert "-----BEGIN ENCRYPTED PRIVATE KEY-----" in out
        assert "-----END ENCRYPTED PRIVATE KEY-----" in out

    def test_double_quote_in_value_is_escaped(self):
        values = {
            "account": 'weird"acct',
            "user": "dbt",
            "private_key": "-----BEGIN KEY-----\nXYZ\n-----END KEY-----\n",
            "private_key_passphrase": "q",
        }
        out = generate_set_env_ps1(values)
        assert 'weird`"acct' in out

    def test_round_trip(self):
        keypair = generate_keys("q")
        account = "roundtrip-acct-9"
        profiles = generate_profiles_yml(account, keypair.private_key_pem_text)

        values = parse_profiles_yml_full(profiles)
        out = generate_set_env_ps1(values)

        assert f'$env:SNOWFLAKE_ACCOUNT = "{account}"' in out


# ===========================================================================
# AppTest UI tests
# ===========================================================================


class TestEnvScriptsUI:
    """Verify the env scripts tab renders."""

    def test_env_scripts_tab_renders_in_default(self):
        """Default mode renders the env-scripts heading and an uploader."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        markdown_blobs = " ".join(m.value for m in at.get("markdown"))
        assert "Download env scripts" in markdown_blobs, (
            "Expected env-scripts tab heading in default-mode markdown"
        )
        # Default mode now has at least 2 uploaders (preset recovery + env scripts).
        assert len(at.get("file_uploader")) >= 2

    def test_env_scripts_tab_absent_in_ceu(self):
        """CEU mode shows no tabs, so no env-scripts heading and no uploader."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        markdown_blobs = " ".join(m.value for m in at.get("markdown"))
        assert "Download env scripts" not in markdown_blobs
        assert len(at.get("file_uploader")) == 0
