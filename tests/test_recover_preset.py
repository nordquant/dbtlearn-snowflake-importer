"""Tests for preset-instructions.md recovery from profiles.yml upload."""

import pytest
from streamlit.testing.v1 import AppTest

from core.keys import generate_keys
from streamlit_app import (
    generate_preset_instructions,
    generate_profiles_yml,
    parse_profiles_yml,
)

# ---------------------------------------------------------------------------
# Fixture constants – generated once from generate_keys() + helpers
# ---------------------------------------------------------------------------
FIXTURE_ACCOUNT = "myorg-myaccount12345"
FIXTURE_PROFILES_YML = """\
airbnb:
  outputs:
    dev:
      type: snowflake
      account: myorg-myaccount12345
      user: dbt

      role: TRANSFORM
      private_key: "-----BEGIN ENCRYPTED PRIVATE KEY-----\\nFAKEKEYDATA0123456789\\n-----END ENCRYPTED PRIVATE KEY-----\\n"
      private_key_passphrase: q

      database: AIRBNB
      schema: DEV
      threads: 1
      warehouse: COMPUTE_WH
  target: dev
"""
FIXTURE_KEY_PEM_TEXT = (
    "-----BEGIN ENCRYPTED PRIVATE KEY-----\\n"
    "FAKEKEYDATA0123456789\\n"
    "-----END ENCRYPTED PRIVATE KEY-----\\n"
)
FIXTURE_PRESET = generate_preset_instructions(FIXTURE_ACCOUNT, FIXTURE_KEY_PEM_TEXT)


# ===========================================================================
# Unit tests for parse_profiles_yml()
# ===========================================================================


class TestParseProfilesYml:
    """Unit tests for parse_profiles_yml()."""

    def test_parse_valid_profiles(self):
        """Generate profiles.yml from known inputs, parse it, verify extracted values match."""
        keypair = generate_keys("q")
        account = "test-org-abc12345"
        profiles = generate_profiles_yml(account, keypair.private_key_pem_text)

        parsed_account, parsed_key = parse_profiles_yml(profiles)

        assert parsed_account == account
        assert parsed_key == keypair.private_key_pem_text

    def test_round_trip_consistency(self):
        """Same profile leads to the same preset file (the key round-trip test)."""
        keypair = generate_keys("q")
        account = "roundtrip-org-99999"

        profiles = generate_profiles_yml(account, keypair.private_key_pem_text)
        preset_original = generate_preset_instructions(
            account, keypair.private_key_pem_text
        )

        parsed_account, parsed_key = parse_profiles_yml(profiles)
        preset_regenerated = generate_preset_instructions(parsed_account, parsed_key)

        assert preset_regenerated == preset_original

    def test_newline_conversion(self):
        """Parsed key has escaped \\n (literal backslash-n), not actual newlines."""
        keypair = generate_keys("q")
        profiles = generate_profiles_yml("acct-123", keypair.private_key_pem_text)

        _, parsed_key = parse_profiles_yml(profiles)

        assert "\\n" in parsed_key
        assert "\n" not in parsed_key

    def test_parse_invalid_yaml(self):
        """Garbage input raises ValueError."""
        with pytest.raises(ValueError, match="Invalid YAML format"):
            parse_profiles_yml(":::not valid yaml:::\n  - ][")

    def test_parse_wrong_structure(self):
        """Valid YAML without airbnb.outputs.dev raises ValueError."""
        with pytest.raises(ValueError, match="Invalid profiles.yml structure"):
            parse_profiles_yml("foo:\n  bar: baz\n")

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
            parse_profiles_yml(yaml_content)

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
            parse_profiles_yml(yaml_content)


# ===========================================================================
# Fixture-based regression test
# ===========================================================================


class TestFixtureRoundTrip:
    """Regression test using hardcoded fixture constants."""

    def test_fixture_round_trip(self):
        """Parse hardcoded profiles.yml fixture, regenerate preset, verify match."""
        account, key = parse_profiles_yml(FIXTURE_PROFILES_YML)
        preset = generate_preset_instructions(account, key)

        assert account == FIXTURE_ACCOUNT
        assert key == FIXTURE_KEY_PEM_TEXT
        assert preset == FIXTURE_PRESET


# ===========================================================================
# AppTest UI tests
# ===========================================================================


class TestPresetRecoveryUI:
    """Verify the recovery expander/file uploader is present on landing pages."""

    def test_recovery_expander_on_default_landing(self):
        """Default mode landing page has the upload_profiles_yml file uploader."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # File uploader widget should exist
        uploader = at.get("file_uploader")
        assert len(uploader) > 0, "Expected file uploader on default landing page"

    def test_recovery_expander_on_ceu_landing(self):
        """CEU mode landing page has the upload_profiles_yml file uploader."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.query_params["course"] = "ceu"
        at.run()

        uploader = at.get("file_uploader")
        assert len(uploader) > 0, "Expected file uploader on CEU landing page"

    def test_recovery_expander_on_capstone_landing(self):
        """Capstone mode landing page has the upload_profiles_yml file uploader."""
        at = AppTest.from_file("streamlit_app.py", default_timeout=30)
        at.run()

        # Switch to capstone mode
        at.radio(key="radio_setup_mode").set_value("Set up Capstone").run()

        uploader = at.get("file_uploader")
        assert len(uploader) > 0, "Expected file uploader on capstone landing page"
