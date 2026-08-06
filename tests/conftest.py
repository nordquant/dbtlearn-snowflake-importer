import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

# Absolute path to the app under test. Streamlit 1.61 resolves a relative
# AppTest.from_file() path against the file that calls it rather than the
# working directory, so a bare "streamlit_app.py" would look inside tests/.
APP_FILE = str(Path(__file__).parent.parent / "streamlit_app.py")

# Load .env only if it exists (local dev)
# Environment variables from CI/GitHub secrets take priority
load_dotenv()


def pytest_configure(config):
    config.addinivalue_line("markers", "ceu: CEU mode tests (only run with [testceu] in commit)")


@pytest.fixture(scope="session")
def snowflake_credentials():
    """Load credentials from env (GitHub secrets) or .env (local).

    GitHub secrets are injected as env vars, which take priority over .env.
    """
    account = os.environ.get("SNOWFLAKE_ACCOUNT")
    username = os.environ.get("SNOWFLAKE_USERNAME")
    password = os.environ.get("SNOWFLAKE_PASSWORD")

    if not all([account, username, password]):
        pytest.skip("SNOWFLAKE_* credentials not set in environment")

    return {"account": account, "username": username, "password": password}
