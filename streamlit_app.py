import json
import logging
import os
import socket
import traceback
from collections import OrderedDict
from contextlib import contextmanager
from logging import getLogger
from urllib.parse import quote_plus

import streamlit as st
import yaml
from cryptography.hazmat.primitives import serialization
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import registry
from sqlalchemy.exc import DatabaseError, InterfaceError

from core.keys import generate_keys
from core.snowflake import extract_snowflake_account, is_valid_snowflake_account
from datetime import datetime, timezone

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
APP_START_TIME = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
# Container ID: in Docker HOSTNAME is the container ID, locally use machine hostname
CONTAINER_ID = os.environ.get("HOSTNAME", socket.gethostname())


def _generate_container_info_file():
    """Generate static/container-info.json for deployment verification.

    This file is served by Streamlit's static file serving and used by the
    deployment script to verify which container is serving traffic.
    Works both locally and in Docker.
    """
    static_dir = os.path.join(CURRENT_DIR, "static")
    os.makedirs(static_dir, exist_ok=True)

    info = {
        "container_id": CONTAINER_ID,
        "git_commit": os.environ.get("GIT_COMMIT", "local"),
        "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    info_path = os.path.join(static_dir, "container-info.json")
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)

    print(f"Container info written to {info_path}: {info}")


# Generate container info file at module load (once per process)
_generate_container_info_file()
sql_sections = {
    "snowflake_setup": "Setting up the dbt User and Roles",
    "snowflake_import": "Importing Raw Tables",
    "capstone_airstats": "Importing AIRSTATS Capstone Tables",
}

# SQL resource files configuration
# Each entry: (filename, required_for_modes) where modes is a list or None for always required
SQL_RESOURCE_FILES = [
    ("course-resources.md", None),  # Always required
    ("capstone-resources.md", None),  # Always required (capstone is now part of standard course)
]


def check_sql_resource_files(course_mode: str) -> list[str]:
    """Check if all required SQL resource files exist.

    Returns a list of warning messages for missing files.
    """
    warnings = []
    for filename, required_modes in SQL_RESOURCE_FILES:
        filepath = os.path.join(CURRENT_DIR, filename)
        is_required = required_modes is None or course_mode in required_modes

        if is_required and not os.path.exists(filepath):
            mode_desc = f" (required for {course_mode} mode)" if required_modes else ""
            warnings.append(
                f"SQL resource file '{filename}' not found{mode_desc}. "
                f"Some features may not work correctly."
            )
            logging.error(f"Missing SQL resource file: {filepath}")

    return warnings


def generate_profiles_yml(snowflake_account: str, private_key_pem_text: str) -> str:
    """Generate profiles.yml content from template with account and private key."""
    template_path = os.path.join(CURRENT_DIR, "profiles.template.yml")

    with open(template_path, "r") as f:
        template_content = f.read()

    # Replace placeholders
    profiles_content = template_content.replace(
        "{{snowflake_account}}", snowflake_account
    ).replace("{{private_key_pem_text}}", private_key_pem_text)

    return profiles_content


def parse_profiles_yml(profiles_content: str) -> tuple[str, str]:
    """Parse profiles.yml and extract snowflake_account and private_key_pem_text.

    Returns (snowflake_account, private_key_pem_text) with escaped \\n in the key.
    Raises ValueError if parsing fails.
    """
    try:
        parsed = yaml.safe_load(profiles_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML format: {e}")

    try:
        dev_config = parsed["airbnb"]["outputs"]["dev"]
    except (KeyError, TypeError):
        raise ValueError("Invalid profiles.yml structure. Expected airbnb.outputs.dev hierarchy.")

    account = dev_config.get("account")
    if not account:
        raise ValueError("Missing 'account' field in profiles.yml")

    private_key = dev_config.get("private_key")
    if not private_key:
        raise ValueError("Missing 'private_key' field in profiles.yml")

    # YAML parses escaped \n in double-quoted strings into actual newlines.
    # Convert back to escaped \n for preset-instructions.md format.
    private_key_pem_text = private_key.replace("\n", "\\n")

    return account, private_key_pem_text


def generate_preset_instructions(
    snowflake_account: str, private_key_pem_text: str
) -> str:
    """Generate preset-instructions.md content with SQLAlchemy URL and Security JSON."""
    # Convert PEM to single line with visible \n

    content = f"""# Preset Instructions

## SQLAlchemy URL
```
snowflake://preset@{snowflake_account}/AIRBNB?role=REPORTER&warehouse=COMPUTE_WH
```

## Security JSON
```json
{{
    "auth_method": "keypair",
    "auth_params": {{
        "privatekey_body": "{private_key_pem_text}",
        "privatekey_pass": "q"
    }}
}}
```

## Instructions
1. Use the SQLAlchemy URL above to connect to your Snowflake database
2. Use the Security JSON configuration for authentication
3. The private key is already formatted with escaped newlines for direct use
""".replace(
        f"{snowflake_account}", snowflake_account
    )

    return content


@contextmanager
def get_snowflake_connection(account, username, password, passcode=None):
    # URL encode the username and password to handle special characters
    encoded_username = quote_plus(username)
    encoded_password = quote_plus(password)

    connection_string = f"snowflake://{encoded_username}:{encoded_password}@{account}/AIRBNB/DEV?warehouse=COMPUTE_WH&role=ACCOUNTADMIN&account_identifier={account}"
    print(connection_string)

    # Add passcode to connect_args if provided (for TOTP-based MFA)
    connect_args = {}
    if passcode:
        connect_args["passcode"] = passcode

    engine = create_engine(connection_string, connect_args=connect_args)
    connection = engine.connect()

    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


@contextmanager
def get_dbt_connection(account, login_name, role, private_key_pem):
    """Connect to Snowflake using dbt user with private key authentication."""

    # URL encode the account to handle special characters
    encoded_login_name = quote_plus(login_name)
    encoded_account = quote_plus(account)

    # Load the private key from PEM format
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"),
        password=b"q",  # The passphrase used to encrypt the key
        backend=None,
    )

    # Convert to DER format (unencrypted) as bytes for connect_args
    private_key_der = private_key.private_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )

    # Create connection string for dbt user (without private_key in URL)
    connection_string = (
        f"snowflake://{encoded_login_name}@{encoded_account}/AIRBNB?"
        f"role={role}&warehouse=COMPUTE_WH&"
        f"account_identifier={encoded_account}"
    )

    print(f"DBT Connection string: {connection_string}")

    # Pass private key via connect_args as required by Snowflake SQLAlchemy
    engine = create_engine(
        connection_string,
        connect_args={
            "private_key": private_key_der,
        },
    )
    connection = engine.connect()

    try:
        yield connection
    finally:
        connection.close()
        engine.dispose()


def streamlit_session_id():
    try:
        from streamlit.runtime import get_instance
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        runtime = get_instance()
        ctx = get_script_run_ctx()
        if ctx is None:
            return "nosession"
        session_id = ctx.session_id
        session_info = runtime._session_mgr.get_session_info(session_id)
        if session_info is None:
            return "nosession"
        return session_info.session.id
    except (AttributeError, TypeError):
        # Running in test environment (AppTest) where runtime is mocked
        return "test-session"


def get_sql_commands(md, public_key=None):
    commands = OrderedDict()
    current_section = None
    in_named_sql = False
    for line in md.split("\n"):
        if in_named_sql:
            if line.startswith("```"):
                in_named_sql = False
            else:
                if line.strip() == "" or line.startswith("--"):
                    continue
                # add command to current section
                if current_section not in commands:
                    commands[current_section] = ""

                # Replace public key placeholder if present and public_key provided
                placeholder = "<<Add Your Public Key File's content here>>"
                if public_key and placeholder in line:
                    line = line.replace(placeholder, public_key)

                commands[current_section] += line + "\n"
        elif line.startswith("```sql {#"):
            in_named_sql = True
            current_section = line.split("{#")[1].split("}")[0]
    return {
        k: [c.strip("\n") for c in v.split(";") if c.strip() != ""]
        for k, v in commands.items()
    }


hello_msg_default = """
# dbt (Data Build Tool) Bootcamp
## Snowflake and Profile Setup Helper

Hi there!

This webapp helps you getting started with dbt, Snowflake and Preset, the BI tool we'll use in the course.

**We'll do the following**:

* **Step 1)** Snowflake Setup - We'll generate a keypair, set up your Snowflake account and import the raw AirBnB tables **and the AIRSTATS capstone database**.
* **Step 2)** Configuration Files - We'll download the configuration files needed for your dbt project and Preset.

On with the setup!
"""

hello_msg_ceu = """
# CEU Modern Data Platforms
## Snowflake and Profile Setup Helper

Hi there!

This webapp helps you getting started with dbt, Snowflake and Preset for the **CEU Modern Data Platforms** course.

**We'll do the following**:

* **Step 1)** Snowflake Setup - We'll generate a keypair, set up your Snowflake account and import the raw AirBnB tables **and the AIRSTATS capstone database**.
* **Step 2)** Configuration Files - We'll download the configuration files needed for your dbt project and Preset.

On with the setup!
"""

hello_msg_capstone = """
# dbt (Data Build Tool) Bootcamp
## Set up Capstone (AIRSTATS Database)

**This mode is only for students who started the course before 20 February 2026.**

If you started after that date, the AIRSTATS capstone database was already set up as part of the standard setup. You don't need to run this again.

**Not sure?** Log in to your Snowflake account and check if you already have an `AIRSTATS` database. If you do, you're all set!

This wizard will:
* Connect to your Snowflake account
* Create the `AIRSTATS` database with airport data tables
* Grant the necessary permissions to your `dbt` and `preset` users
"""


logging.root.setLevel(logging.INFO)
logger = getLogger(__name__)
logger.Formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)


GITHUB_REPO_URL = "https://github.com/nordquant/dbtlearn-snowflake-importer"


def get_build_info() -> str:
    """Get build info for footer display."""
    commit_full = os.environ.get("GIT_COMMIT", "local")
    commit_short = commit_full[:7]
    if commit_full not in ("local", "unknown"):
        commit_link = f'<a href="{GITHUB_REPO_URL}/commit/{commit_full}" target="_blank" style="color: #888;">{commit_short}</a>'
    else:
        commit_link = commit_short
    # HOSTNAME is automatically set by Docker to the container ID
    container_id = os.environ.get("HOSTNAME", "unknown")[:12]
    return f"commit: {commit_link} | container: {container_id} | started: {APP_START_TIME} UTC"


def render_credentials_form(key_prefix=""):
    """Render Snowflake credentials form. Returns (hostname, username, password, passcode).

    Args:
        key_prefix: Prefix for widget keys to avoid conflicts when rendered in multiple tabs.
    """
    registry.register("snowflake", "snowflake.sqlalchemy", "dialect")

    # Check environment for credentials (priority: env vars, then defaults)
    env_account = os.environ.get("SNOWFLAKE_ACCOUNT", "xxxxxx-xxxxxxxx")
    env_username = os.environ.get("SNOWFLAKE_USERNAME", "admin")
    env_password = os.environ.get("SNOWFLAKE_PASSWORD", "")

    st.info(
        "Now let's add your Snowflake Account name and Admin Credentials so we can set up the permissions and the datasets for you."
    )
    hostname_raw = st.text_input(
        "Snowflake account (this looks like as `frgcsyo-ie17820` or `frgcsyo-ie17820.aws`, check your snowlake registration email).\n\n_**This is not your Snowflake username**, but the first part of the snowflake url you received in your snowflake registration email_. You can also paste the full url from the registration email:",
        env_account,
        key=f"{key_prefix}input_snowflake_account",
    )
    hostname = extract_snowflake_account(hostname_raw)

    # Check if the account format is valid
    account_is_valid = is_valid_snowflake_account(hostname)

    # Store the account in session state for later use
    st.session_state.snowflake_account = hostname

    if hostname_raw.strip() != "xxxxxx-xxxxxxxx" and not account_is_valid:
        st.warning(
            "This doesn't look like a valid Snowflake account format. Please check your account identifier."
        )
    else:
        # Show the extracted account identifier if it's different from the input
        if hostname != hostname_raw and hostname_raw.strip() != "xxxxxx-xxxxxxxx":
            st.info(f"Using account identifier: `{hostname}`")
    username = st.text_input(
        "Snowflake username (change this is you didn't set it to `admin` at registration):",
        env_username,
        key=f"{key_prefix}input_snowflake_username",
    )
    password = st.text_input(
        "Snowflake Password:",
        env_password,
        type="password",
        key=f"{key_prefix}input_snowflake_password",
    )

    st.warning(
        "Snowflake has been rolling out an update gradually which enforces **Multi Factor Authentication (MFA)**. If you have been enrolled to MFA, a push notification will be sent to your DUO app after you click _Start Setup_. If this happens, please approve the request and the setup will continue automatically.\n\n"
        "**If you use TOTP-based MFA** (Google/Microsoft Authenticator, or Duo TOTP), check the box below and enter your 6-digit code."
    )

    use_totp = st.checkbox(
        "I use TOTP-based MFA (authenticator app that generates 6-digit codes)",
        key=f"{key_prefix}checkbox_use_totp",
        help="Check this if you use an authenticator app like Google Authenticator, Microsoft Authenticator, or Duo TOTP"
    )

    passcode = None
    if use_totp:
        passcode = st.text_input(
            "Enter your 6-digit TOTP code:",
            max_chars=6,
            key=f"{key_prefix}input_totp_passcode",
            help="Open your authenticator app and enter the current 6-digit code for Snowflake"
        )

    return hostname, username, password, passcode


def _connect_to_snowflake(session_id, hostname, username, password, passcode):
    """Attempt to connect to Snowflake. Returns (connection_cm, connection) or displays error and returns None."""
    try:
        with st.status("Connecting to Snowflake"):
            connection_cm = get_snowflake_connection(hostname, username, password, passcode)
            connection = connection_cm.__enter__()
        return connection_cm, connection
    except InterfaceError as e:
        st.error(
            f"""Error connecting to Snowflake. This usually means that the snowflake account is invalid.
            Please verify the snowflake account and try again.\n\nOriginal Error: \n\n{e.orig}"""
        )
        logging.warning(
            f"{session_id}: Error connecting to Snowflake. Account: {hostname}, Username: {username}: {e}"
        )
        return None
    except DatabaseError as e:
        print(e)
        error_str = str(e.orig) if hasattr(e, 'orig') else str(e)

        # Check if this is a TOTP MFA error
        if "TOTP is required" in error_str or "MFA with TOTP" in error_str:
            st.error(
                "**Your Snowflake account requires TOTP-based MFA.**\n\n"
                "Please check the **'I use TOTP-based MFA'** checkbox above and enter "
                "the 6-digit code from your authenticator app (Google Authenticator, "
                "Microsoft Authenticator, or Duo TOTP).\n\n"
                f"Original Error:\n\n{e.orig}"
            )
        else:
            st.error(
                f"Error connecting to Snowflake. This usually means that the snowflake username or password you provided is not valid. Please correct them and retry by pressing the Start Setup button.\n\nOriginal Error:\n\n{e.orig}"
            )
        logging.warning(
            f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}"
        )
        return None
    except Exception as e:

        st.error(
            f"Error connecting to Snowflake.\n\nOriginal Error:\n\n{e}\n\nStacktrace:\n\n{traceback.format_exc()}"
        )
        logging.warning(
            f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}\nStacktrace:\n{traceback.format_exc()}"
        )
        return None


def _execute_sql_sections(session_id, connection, sql_commands, sections_to_run):
    """Execute SQL sections and verify tables. Returns True on success."""
    try:
        # Log sections being executed for debugging
        print(f"DEBUG [{session_id}]: === EXECUTING SQL SECTIONS ===")
        print(f"DEBUG [{session_id}]: Sections to execute: {sections_to_run}")
        logging.info(f"{session_id}: SQL sections to execute: {sections_to_run}")

        for section in sections_to_run:
            commands = sql_commands[section]
            print(f"DEBUG [{session_id}]: EXECUTING section: {section} with {len(commands)} commands")
            logging.info(f"{session_id}: Executing section: {section} with {len(commands)} commands")
            with st.status(
                sql_sections[section]
            ) as internal_status_spinner:
                for command in commands:
                    st.write(f"Executing command: `{command}`")
                    connection.execute(text(command))
                    connection.commit()

        return True
    except Exception as e:
        st.error(
            f"Error executing command.\n\nOriginal Error:\n\n{e}\n\nTraceback:\n\n{traceback.format_exc()}"
        )
        logging.warning(
            f"{session_id}: Error executing SQL. Account name: {st.session_state.get('snowflake_account')}\n Original Error: {e}"
        )
        return False


def _verify_tables(connection, tables):
    """Verify that tables have rows. Returns True if all tables have data."""
    for table in tables:
        result = connection.execute(
            text(f"SELECT COUNT(*) FROM {table}")
        )
        count = result.fetchone()[0]
        if count == 0:
            st.error(
                f"Table {table} has no rows. This is unexpected. Please check the logs and try again."
            )
            return False
    return True


def _verify_user_connections(session_id, hostname):
    """Verify dbt and preset user connections. Returns True on success."""
    try:
        private_key_pem = st.session_state.keypair.private_key
        for users in [
            ("dbt", "TRANSFORM", "RAW"),
            ("preset", "REPORTER", "DEV"),
        ]:
            with st.status(
                f"Verifying connection with {users[0]} user"
            ) as internal_status_spinner:
                with get_dbt_connection(
                    hostname, users[0], users[1], private_key_pem
                ) as dbt_connection:
                    dbt_connection.execute(
                        text(f"USE ROLE {users[1]}")
                    )
                    dbt_connection.execute(
                        text(f"USE DATABASE AIRBNB")
                    )
                    dbt_connection.execute(
                        text(f"USE SCHEMA {users[2]}")
                    )

                    if users[0] == "dbt":
                        # Query RAW_LISTINGS table using dbt user
                        query = "SELECT * FROM RAW.RAW_LISTINGS"
                        dbt_result = dbt_connection.execute(text(query))
                        dbt_result.fetchone()

                internal_status_spinner.success(
                    f"Success connecting as {users[0]} user"
                )
        return True

    except Exception as e:
        error_msg = (
            f"Failed to connect with user or query "
            f"RAW_LISTINGS: {str(e)}"
        )
        st.error(error_msg)
        st.warning(
            "This might indicate an issue with the user "
            "setup or permissions."
        )
        logging.warning(
            f"{session_id}: user connection failed: {e}\nTraceback:\n{traceback.format_exc()}"
        )
        return False


def _render_preset_recovery_standalone():
    """Render the preset file recovery UI as a standalone tab."""
    st.markdown(
        "## Re-download Preset Instructions\n\n"
        "If you still have your `profiles.yml` but lost your "
        "`preset-instructions.md`, upload it here to regenerate it."
    )
    uploaded = st.file_uploader(
        "Upload your profiles.yml",
        type=["yml", "yaml"],
        key="upload_profiles_yml",
    )
    if uploaded is not None:
        try:
            content = uploaded.read().decode("utf-8")
            account, key = parse_profiles_yml(content)
            preset = generate_preset_instructions(account, key)
            st.download_button(
                label="Download preset-instructions.md",
                data=preset,
                file_name="preset-instructions.md",
                mime="text/markdown",
                key="btn_download_recovered_preset",
            )
            st.success("Preset instructions regenerated successfully!")
        except ValueError as e:
            st.error(f"Could not parse profiles.yml: {e}")


def standard_setup(session_id):
    """Standard setup flow: landing -> Snowflake setup (with keypair) -> download config files."""
    is_ceu_mode = st.session_state.course_mode == "ceu"

    if "step_standard" not in st.session_state:
        st.session_state.step_standard = 0

    # Step 0: Landing Page
    if st.session_state.step_standard == 0:
        hello_msg = hello_msg_ceu if is_ceu_mode else hello_msg_default
        st.markdown(hello_msg)

        if st.button(
            "Start Setup Process",
            type="primary",
            use_container_width=True,
            key="btn_start_setup",
        ):
            st.session_state.step_standard = 1
            st.rerun()

    # Step 1: Snowflake Setup (keypair generation + credentials + SQL execution)
    elif st.session_state.step_standard == 1:
        snowflake_setup_complete = False
        st.markdown("### Step 1: Snowflake Setup")

        if st.button("Back to Welcome", type="secondary", key="btn_back_to_welcome"):
            st.session_state.step_standard = 0
            st.rerun()

        # Generate keypair silently
        if "keypair" not in st.session_state:
            with st.status("Generating keypair..."):
                st.session_state.keypair = generate_keys("q")
                st.markdown(" Private Key (rsa_key.p8) generated")
                st.markdown(" Public Key (rsa_key.pub) generated")
        keypair = st.session_state.keypair

        # Keypair download in expander
        with st.expander("Advanced: Download keypair files"):
            st.info(
                "These keypair files are automatically used during setup. You only need to download them if you want a backup copy."
            )
            st.download_button(
                label="Download Private Key (rsa_key.p8)",
                data=keypair.private_key,
                file_name="rsa_key.p8",
                mime="text/plain",
                key="btn_download_private_key",
            )
            st.download_button(
                label="Download Public Key (rsa_key.pub)",
                data=keypair.public_key,
                file_name="rsa_key.pub",
                mime="text/plain",
                key="btn_download_public_key",
            )

        # Credentials form
        hostname, username, password, passcode = render_credentials_form(key_prefix="std_")

        if st.button("Start Setup", key="btn_start_snowflake_setup"):
            if len(password) == 0:
                st.error("Please provide a password")
                return

            # Load and process SQL commands with public key substitution
            with open(CURRENT_DIR + "/course-resources.md", "r") as file:
                md = file.read().rstrip()
            public_key = st.session_state.keypair.public_key
            sql_commands = get_sql_commands(md, public_key)

            # Always load capstone SQL
            capstone_path = CURRENT_DIR + "/capstone-resources.md"
            print(f"DEBUG [{session_id}]: Loading capstone from {capstone_path}")
            logging.info(f"{session_id}: Loading capstone from {capstone_path}, exists={os.path.exists(capstone_path)}")
            if os.path.exists(capstone_path):
                with open(capstone_path, "r") as file:
                    capstone_md = file.read().rstrip()
                capstone_commands = get_sql_commands(capstone_md, public_key)
                print(f"DEBUG [{session_id}]: Capstone sections loaded: {list(capstone_commands.keys())}")
                logging.info(f"{session_id}: Capstone sections loaded: {list(capstone_commands.keys())}")
                sql_commands = {**sql_commands, **capstone_commands}
            else:
                print(f"DEBUG [{session_id}]: ERROR - capstone file does not exist!")
                logging.error(f"{session_id}: Capstone file not found at {capstone_path}")

            # Connect to Snowflake
            result = _connect_to_snowflake(session_id, hostname, username, password, passcode)
            if result is None:
                return
            connection_cm, connection = result

            try:
                with st.status(
                    "Setting up your Snowflake account (this can take up to 2 minutes)"
                ) as status_spinner:
                    # Execute all SQL sections
                    sections_to_run = [s for s in sql_commands.keys()]
                    if not _execute_sql_sections(session_id, connection, sql_commands, sections_to_run):
                        status_spinner.update(
                            label="Error executing command",
                            state="error",
                            expanded=True,
                        )
                        return

                    # Verify AIRBNB tables
                    airbnb_tables = [
                        "AIRBNB.RAW.RAW_LISTINGS",
                        "AIRBNB.RAW.RAW_HOSTS",
                        "AIRBNB.RAW.RAW_REVIEWS",
                    ]
                    if not _verify_tables(connection, airbnb_tables):
                        return

                    # Verify AIRSTATS tables
                    airstats_tables = [
                        "AIRSTATS.RAW.AIRPORTS",
                        "AIRSTATS.RAW.AIRPORT_COMMENTS",
                        "AIRSTATS.RAW.RUNWAYS",
                    ]
                    if not _verify_tables(connection, airstats_tables):
                        return

                    # Verify user connections
                    if not _verify_user_connections(session_id, hostname):
                        status_spinner.update(
                            label="Error verifying user connections",
                            state="error",
                            expanded=True,
                        )
                        return

                    snowflake_setup_complete = True
            finally:
                connection_cm.__exit__(None, None, None)

            if snowflake_setup_complete:
                success_msg = "Snowflake Setup complete! Let's continue with downloading the configuration files!"
                st.toast(success_msg, icon="🔥")
                status_spinner.success(success_msg, icon="🔥")

                st.session_state.step_standard = 2
                if st.button(
                    "Download Configuration Files",
                    type="primary",
                    key="btn_goto_downloads",
                ):
                    st.rerun()

    # Step 2: Download Configuration Files
    elif st.session_state.step_standard == 2:
        st.markdown("### Step 1: Snowflake Setup - Completed")
        st.markdown("### Step 2: Download Configuration Files")

        # Add back button
        if st.button(
            "Back to Snowflake Setup", type="secondary", key="btn_back_to_snowflake"
        ):
            st.session_state.step_standard = 1
            st.rerun()

        st.markdown(
            """Download the configuration files needed for dbt and Preset integration.

 * `profiles.yml`: contains your dbt connection configuration which you'll need to copy to your dbt project folder later.
 * `preset-instructions.md`: contains instructions for connecting to Preset, which we'll cover later in the course."""
        )

        # Get the keypair and account info from session state
        if "keypair" not in st.session_state:
            st.error("No keypair found. Please go back and generate keys first.")
            return

        if "snowflake_account" not in st.session_state:
            st.error(
                "No Snowflake account found. Please go back and complete "
                "Snowflake setup first."
            )
            return

        keypair = st.session_state.keypair
        snowflake_account = st.session_state.snowflake_account

        # Generate the files
        profiles_content = generate_profiles_yml(
            snowflake_account, keypair.private_key_pem_text
        )
        preset_content = generate_preset_instructions(
            snowflake_account, keypair.private_key_pem_text
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### ① dbt profiles.yml")
            st.markdown("This file contains your dbt connection configuration.")
            st.download_button(
                label="Download profiles.yml",
                data=profiles_content,
                file_name="profiles.yml",
                mime="text/yaml",
                key="btn_download_profiles",
            )

        with col2:
            st.markdown("#### ② Preset Instructions")
            st.markdown("This file contains instructions for connecting to Preset.")
            st.download_button(
                label="Download preset-instructions.md",
                data=preset_content,
                file_name="preset-instructions.md",
                mime="text/markdown",
                key="btn_download_preset",
            )

        st.success("Configuration files ready for download!")
        st.info(
            "Please download **both** files above. You'll need them to configure "
            "dbt and Preset with your Snowflake database."
        )

        st.toast("Configuration files ready for download!", icon="🔥")
        st.success(
            "Once you downloaded both files, you can go back to the course and continue with the setup!"
        )


def capstone_setup(session_id):
    """Capstone-only setup flow: landing -> credentials + AIRSTATS SQL execution."""

    if "step_capstone" not in st.session_state:
        st.session_state.step_capstone = 0

    # Step 0: Capstone Landing Page
    if st.session_state.step_capstone == 0:
        st.markdown(hello_msg_capstone)

        if st.button(
            "Set up AIRSTATS Capstone",
            type="primary",
            use_container_width=True,
            key="btn_start_capstone",
        ):
            st.session_state.step_capstone = 1
            st.rerun()

    # Step 1: Credentials + AIRSTATS Setup
    elif st.session_state.step_capstone == 1:
        capstone_setup_complete = False
        st.markdown("### Set up AIRSTATS Capstone Database")

        if st.button("Back to Welcome", type="secondary", key="btn_capstone_back_to_welcome"):
            st.session_state.step_capstone = 0
            st.rerun()

        # Credentials form
        hostname, username, password, passcode = render_credentials_form(key_prefix="cap_")

        if st.button("Start Capstone Setup", key="btn_start_capstone_setup"):
            if len(password) == 0:
                st.error("Please provide a password")
                return

            # Load capstone SQL only
            capstone_path = CURRENT_DIR + "/capstone-resources.md"
            if not os.path.exists(capstone_path):
                st.error("Capstone resource file not found. Please contact support.")
                logging.error(f"{session_id}: Capstone file not found at {capstone_path}")
                return

            with open(capstone_path, "r") as file:
                capstone_md = file.read().rstrip()
            sql_commands = get_sql_commands(capstone_md)

            # Connect to Snowflake
            result = _connect_to_snowflake(session_id, hostname, username, password, passcode)
            if result is None:
                return
            connection_cm, connection = result

            try:
                with st.status(
                    "Setting up AIRSTATS capstone database"
                ) as status_spinner:
                    # Execute capstone SQL sections
                    sections_to_run = [s for s in sql_commands.keys()]
                    if not _execute_sql_sections(session_id, connection, sql_commands, sections_to_run):
                        status_spinner.update(
                            label="Error executing command",
                            state="error",
                            expanded=True,
                        )
                        return

                    # Verify AIRSTATS tables
                    airstats_tables = [
                        "AIRSTATS.RAW.AIRPORTS",
                        "AIRSTATS.RAW.AIRPORT_COMMENTS",
                        "AIRSTATS.RAW.RUNWAYS",
                    ]
                    if not _verify_tables(connection, airstats_tables):
                        return

                    capstone_setup_complete = True
            finally:
                connection_cm.__exit__(None, None, None)

            if capstone_setup_complete:
                success_msg = "AIRSTATS Capstone Database setup complete!"
                st.toast(success_msg, icon="🔥")
                status_spinner.success(success_msg, icon="🔥")
                st.success(
                    "The AIRSTATS database has been created with airports, airport_comments, and runways tables. "
                    "You can now go back to the course and continue with the capstone project!"
                )


def main():
    session_id = streamlit_session_id()
    logger.info("Starting Streamlit app")

    # Detect course mode from query params
    course_mode = st.query_params.get("course", "default")
    if "course_mode" not in st.session_state:
        st.session_state.course_mode = course_mode
    is_ceu_mode = st.session_state.course_mode == "ceu"

    # Check for missing SQL resource files and display warnings
    resource_warnings = check_sql_resource_files(st.session_state.course_mode)
    for warning in resource_warnings:
        st.warning(f"⚠️ {warning}")

    if is_ceu_mode:
        # CEU: standard setup with CEU branding, no tabs
        standard_setup(session_id)
    else:
        tab_default, tab_capstone, tab_preset = st.tabs(
            ["Default Setup", "Capstone Only Setup", "Re-download Preset Instructions"]
        )
        with tab_default:
            standard_setup(session_id)
        with tab_capstone:
            capstone_setup(session_id)
        with tab_preset:
            _render_preset_recovery_standalone()

    # Development info footer
    st.markdown(
        f"<div style='position: fixed; bottom: 0; right: 0; padding: 4px 8px; "
        f"font-size: 10px; color: #888; background: rgba(255,255,255,0.9);'>"
        f"{get_build_info()}</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    print("Starting Streamlit app")
    main()
