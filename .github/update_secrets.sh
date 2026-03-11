#!/usr/bin/env bash
#
# Reads secrets from .env and updates them as GitHub repository secrets.
# Usage: .github/update_secrets.sh [path/to/.env]
#
set -euo pipefail

ENV_FILE="${1:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: $ENV_FILE not found"
    exit 1
fi

# Ensure gh CLI is authenticated
if ! gh auth status &>/dev/null; then
    echo "Error: gh CLI is not authenticated. Run 'gh auth login' first."
    exit 1
fi

count=0
while IFS= read -r line; do
    # Skip empty lines and comments
    [[ -z "$line" || "$line" =~ ^# ]] && continue

    key="${line%%=*}"
    value="${line#*=}"

    echo "Setting $key..."
    echo "$value" | gh secret set "$key"
    ((count++))
done < "$ENV_FILE"

echo "Done. Updated $count secret(s)."
