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
    - "JL05209.ap-southeast-3.aws.snowflakecomputing.com" -> "JL05209.ap-southeast-3.aws"
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

    # If it ends with .snowflakecomputing.com, extract the account identifier
    # (everything before .snowflakecomputing.com)
    snowflake_match = re.match(r"^(.+)\.snowflakecomputing\.com$", input_text)
    if snowflake_match:
        return snowflake_match.group(1)

    # For non-snowflakecomputing.com inputs, validate format
    # Match simple account identifiers (with optional hyphen and optional .aws suffix)
    account_match = re.match(
        r"^([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?(?:\.[a-zA-Z0-9-]+)*(?:\.aws)?)$", input_text
    )

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
    - JL05209.ap-southeast-3.aws (regional format)
    - myaccount-123.us-east-1.aws (regional format)

    Args:
        account (str): The account identifier to validate

    Returns:
        bool: True if the account format is valid, False otherwise
    """
    if not account or account.strip() == "":
        return False

    # Pattern for valid Snowflake account:
    # - Starts with alphanumeric
    # - Optionally followed by hyphen and alphanumeric (e.g., abc-def)
    # - Optionally followed by dot-separated segments (for regional identifiers)
    # Examples: frgcsyo-ie17820, frgcsyo-ie17820.aws, JL05209.ap-southeast-3.aws
    pattern = r"^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?(?:\.[a-zA-Z0-9-]+)*$"
    return bool(re.match(pattern, account))
