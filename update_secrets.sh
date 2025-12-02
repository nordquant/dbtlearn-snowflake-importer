#!/bin/bash
# Push Snowflake credentials from .env to GitHub secrets
# Requires: gh CLI authenticated with repo access

set -e

# import GitHub Token
onepass

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed"
    echo "Install it with: brew install gh"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI"
    echo "Run: gh auth login"
    exit 1
fi

# Load .env file
if [ ! -f .env ]; then
    echo "Error: .env file not found"
    echo "Create .env from .env.example and fill in your credentials"
    exit 1
fi

# Source the .env file
set -a
source .env
set +a

# Validate required variables
if [ -z "$SNOWFLAKE_ACCOUNT" ] || [ -z "$SNOWFLAKE_USERNAME" ] || [ -z "$SNOWFLAKE_PASSWORD" ]; then
    echo "Error: Missing required environment variables"
    echo "Ensure SNOWFLAKE_ACCOUNT, SNOWFLAKE_USERNAME, and SNOWFLAKE_PASSWORD are set in .env"
    exit 1
fi

echo "Pushing secrets to GitHub..."

gh secret set SNOWFLAKE_ACCOUNT --body "$SNOWFLAKE_ACCOUNT"
echo "  SNOWFLAKE_ACCOUNT"

gh secret set SNOWFLAKE_USERNAME --body "$SNOWFLAKE_USERNAME"
echo "  SNOWFLAKE_USERNAME"

gh secret set SNOWFLAKE_PASSWORD --body "$SNOWFLAKE_PASSWORD"
echo "  SNOWFLAKE_PASSWORD"

echo "Done! Secrets updated successfully."
