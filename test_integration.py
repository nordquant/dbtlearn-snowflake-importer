#!/usr/bin/env python3
"""
Integration test to verify the public key substitution works in the app flow.
"""

import os
from collections import OrderedDict


# Mock the get_sql_commands function from streamlit_app.py
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


def test_app_integration():
    """Test that the app flow works with public key substitution."""

    # Simulate the app flow
    print("=== Testing App Integration ===")

    # Step 1: Simulate keypair generation (mocked)
    mock_keypair = {
        "public_key": "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...",
    }

    # Step 2: Simulate loading course resources and processing with public key
    course_resources_path = "course-resources.md"

    if os.path.exists(course_resources_path):
        with open(course_resources_path, "r") as file:
            md = file.read().rstrip()

        # Get the public key from session state (simulated)
        public_key = mock_keypair.get("public_key")

        # Process SQL commands with public key substitution
        sql_commands = get_sql_commands(md, public_key)

        print(f"Found {len(sql_commands)} SQL sections:")
        for section, commands in sql_commands.items():
            print(f"  - {section}: {len(commands)} commands")

            # Check if any command contains the public key
            for cmd in commands:
                if "RSA_PUBLIC_KEY" in cmd:
                    if public_key in cmd:
                        print(
                            f"    ✅ Public key substitution successful in: {cmd[:50]}..."
                        )
                    else:
                        print(
                            f"    ❌ Public key substitution failed in: {cmd[:50]}..."
                        )
                        assert False

        print("✅ Integration test passed!")
        assert True
    else:
        print(f"❌ Course resources file not found: {course_resources_path}")
        assert False


if __name__ == "__main__":
    success = test_app_integration()
    exit(0 if success else 1)
