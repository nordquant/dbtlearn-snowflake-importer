import re


def extract_snowflake_account(raw_input):
    """
    Extract Snowflake account identifier from various input formats.

    Examples:
    - "jdehewj-vmb00970" -> "jdehewj-vmb00970"
    - "jhkfheg-qb43765.snowflakecomputing.com" -> "jhkfheg-qb43765"
    - "https://jhkfheg-qb43765.snowflakecomputing.com/console/login" -> "jhkfheg-qb43765"
    - "jdehewj-vmb00970.aws" -> "jdehewj-vmb00970.aws"
    - "xxxxxx.aws" -> "xxxxxx.aws"
    """
    if not raw_input or raw_input.strip() == "":
        return raw_input

    # Remove any leading/trailing whitespace and extra text
    input_text = raw_input.strip()

    # Extract from URL if it's a full URL (supports http, https, and snowflake protocols)
    # Only match if it starts with a protocol
    if input_text.startswith(("http://", "https://", "snowflake://")):
        url_match = re.search(r"(?:https?|snowflake)://([^/]+)", input_text)
        if url_match:
            input_text = url_match.group(1)

    # Remove .snowflakecomputing.com suffix if present
    input_text = re.sub(r"\.snowflakecomputing\.com.*$", "", input_text)

    # Extract the account identifier pattern
    # First try to match the full pattern with .aws
    account_match = re.match(
        r"^([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?(?:\.[a-zA-Z0-9-]+)*\.aws)$", input_text
    )

    # If no .aws pattern matches, try the simpler pattern
    if not account_match:
        account_match = re.match(r"^([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?)$", input_text)

    if account_match:
        return account_match.group(1)

    # If no pattern matches, return original input (fallback)
    return raw_input


def is_valid_snowflake_account(account):
    """
    Check if the account looks like a valid Snowflake account format.

    Valid formats:
    - frgcsyo-ie17820
    - frgcsyo-ie17820.aws
    - abc123.aws
    - singleword

    Args:
        account (str): The account identifier to validate

    Returns:
        bool: True if the account format is valid, False otherwise
    """
    if not account or account.strip() == "":
        return False

    # Pattern for valid Snowflake account: letters, numbers, hyphens, and optionally .aws
    # Examples: frgcsyo-ie17820, frgcsyo-ie17820.aws, abc123.aws
    pattern = r"^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?(?:\.aws)?$"
    return bool(re.match(pattern, account))
