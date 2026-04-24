"""
Test for public key substitution in get_sql_commands function.
"""

from collections import OrderedDict

import pytest


def get_sql_commands(md, public_key=None):
    """Extract SQL commands from markdown and optionally substitute public key."""
    commands = OrderedDict()
    current_section = None
    in_named_sql = False
    for l in md.split("\n"):
        if in_named_sql:
            if l.startswith("```"):
                in_named_sql = False
            else:
                if l.strip() == "" or l.startswith("--"):
                    continue
                # add command to current section
                if current_section not in commands:
                    commands[current_section] = ""

                # Replace public key placeholder if present and public_key provided
                placeholder = "<<Add Your Public Key File's content here>>"
                if public_key and placeholder in l:
                    l = l.replace(placeholder, public_key)

                commands[current_section] += l + "\n"
        elif l.startswith("```sql {#"):
            in_named_sql = True
            current_section = l.split("{#")[1].split("}")[0]
    return {
        k: [c.strip("\n") for c in v.split(";") if c.strip() != ""]
        for k, v in commands.items()
    }


class TestPublicKeySubstitution:
    """Test cases for public key substitution functionality."""

    def test_without_public_key_placeholder_remains(self):
        """Test that placeholder remains when no public key is provided."""
        test_md = """
```sql {#snowflake_setup}
CREATE USER PRESET
  LOGIN_NAME='preset'
  TYPE=SERVICE
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";
```
"""
        result = get_sql_commands(test_md)

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Find the command with the RSA_PUBLIC_KEY
        rsa_command = None
        for cmd in commands:
            if "RSA_PUBLIC_KEY" in cmd:
                rsa_command = cmd
                break

        assert rsa_command is not None
        assert "<<Add Your Public Key File's content here>>" in rsa_command

    def test_with_public_key_placeholder_replaced(self):
        """Test that placeholder is replaced when public key is provided."""
        test_md = """
```sql {#snowflake_setup}
CREATE USER PRESET
  LOGIN_NAME='preset'
  TYPE=SERVICE
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";
```
"""
        test_public_key = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."

        result = get_sql_commands(test_md, test_public_key)

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Find the command with the RSA_PUBLIC_KEY
        rsa_command = None
        for cmd in commands:
            if "RSA_PUBLIC_KEY" in cmd:
                rsa_command = cmd
                break

        assert rsa_command is not None
        assert test_public_key in rsa_command
        assert "<<Add Your Public Key File's content here>>" not in rsa_command

    def test_multiple_placeholders_replaced(self):
        """Test that multiple placeholders are replaced when public key is provided."""
        test_md = """
```sql {#snowflake_setup}
CREATE USER PRESET
  LOGIN_NAME='preset'
  TYPE=SERVICE
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";

CREATE USER ANOTHER_USER
  LOGIN_NAME='another'
  TYPE=SERVICE
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";
```
"""
        test_public_key = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."

        result = get_sql_commands(test_md, test_public_key)

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Count how many commands contain the public key
        public_key_commands = [cmd for cmd in commands if test_public_key in cmd]
        assert len(public_key_commands) == 2

        # Ensure no placeholders remain
        all_commands_text = " ".join(commands)
        assert "<<Add Your Public Key File's content here>>" not in all_commands_text

    def test_no_placeholder_no_substitution(self):
        """Test that commands without placeholders are unchanged."""
        test_md = """
```sql {#snowflake_setup}
CREATE ROLE REPORTER;
SELECT * FROM RAW_LISTINGS LIMIT 10;
```
"""
        test_public_key = "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA..."

        result = get_sql_commands(test_md, test_public_key)

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Commands should be unchanged
        assert "CREATE ROLE REPORTER" in commands
        assert "SELECT * FROM RAW_LISTINGS LIMIT 10" in commands
        assert test_public_key not in " ".join(commands)

    def test_empty_public_key_no_substitution(self):
        """Test that empty public key results in no substitution."""
        test_md = """
```sql {#snowflake_setup}
CREATE USER PRESET
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";
```
"""
        result = get_sql_commands(test_md, "")

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Placeholder should remain
        all_commands_text = " ".join(commands)
        assert "<<Add Your Public Key File's content here>>" in all_commands_text

    def test_none_public_key_no_substitution(self):
        """Test that None public key results in no substitution."""
        test_md = """
```sql {#snowflake_setup}
CREATE USER PRESET
  RSA_PUBLIC_KEY="<<Add Your Public Key File's content here>>";
```
"""
        result = get_sql_commands(test_md, None)

        assert "snowflake_setup" in result
        commands = result["snowflake_setup"]

        # Placeholder should remain
        all_commands_text = " ".join(commands)
        assert "<<Add Your Public Key File's content here>>" in all_commands_text


class TestLegacySetupSection:
    """Verify the legacy username/password SQL lives in its own file."""

    def _load(self, filename):
        import os
        import sys

        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from streamlit_app import get_sql_commands as real_get_sql_commands
        from streamlit_app import CURRENT_DIR

        with open(f"{CURRENT_DIR}/{filename}", "r") as f:
            return real_get_sql_commands(f.read())

    def test_snowflake_setup_legacy_parsed(self):
        commands = self._load("course-resources-legacy.md")
        assert "snowflake_setup_legacy" in commands
        joined = " ".join(commands["snowflake_setup_legacy"]).upper()
        assert "PASSWORD=" in joined
        assert "LEGACY_SERVICE" in joined
        assert "<<ADD YOUR PUBLIC KEY" not in joined

    def test_course_resources_unchanged(self):
        """Legacy section must live in the separate file, not course-resources.md."""
        commands = self._load("course-resources.md")
        assert "snowflake_setup_legacy" not in commands


if __name__ == "__main__":
    pytest.main([__file__])
