import re

# Snowsight (the Snowflake web UI) doesn't put the account in the hostname —
# every account is served from this one host and identified by the path.
SNOWSIGHT_HOST = "app.snowflake.com"

# Cloud region segments as they appear in legacy Snowsight URLs, e.g.
# "us-east-1", "eu-central-1", "us-central1.gcp". Distinguishable from an
# organization name by the trailing digit.
_REGION_SEGMENT = re.compile(r"^[a-z]{2}-[a-z0-9-]*\d(?:\.(?:aws|gcp|azure))?$")


def _extract_from_snowsight_url(input_text):
    """Pull the account identifier out of a Snowsight URL's path.

    Snowsight addresses an account with two path segments:
    - organization form: `app.snowflake.com/<org>/<account>/#/...` -> `<org>-<account>`
    - legacy region form: `app.snowflake.com/<region>/<locator>/...` -> `<locator>.<region>`

    Returns None when the URL carries no usable path, so the caller can fall
    back and let validation reject it — `app.snowflake.com` is the same host
    for every customer and is never itself an account identifier.
    """
    remainder = input_text.split(SNOWSIGHT_HOST, 1)[1]
    path = remainder.split("#")[0].split("?")[0]
    segments = [segment for segment in path.split("/") if segment]

    if len(segments) < 2:
        return None

    first, second = segments[0], segments[1]
    if _REGION_SEGMENT.match(first):
        return f"{second}.{first}"
    return f"{first}-{second}"


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
    - "https://app.snowflake.com/qfxfhpj/nub20832/#/workspaces" -> "qfxfhpj-nub20832"
    """
    if not raw_input or raw_input.strip() == "":
        return raw_input

    # Remove any leading/trailing whitespace and extra text
    input_text = raw_input.strip()

    # Snowsight URLs must be handled before the host is isolated below: the
    # account lives in the path, and the host is the same for everyone.
    if SNOWSIGHT_HOST in input_text:
        return _extract_from_snowsight_url(input_text) or raw_input

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
