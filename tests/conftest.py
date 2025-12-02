import os

import pytest
from dotenv import load_dotenv

# Load .env only if it exists (local dev)
# Environment variables from CI/GitHub secrets take priority
load_dotenv()


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
