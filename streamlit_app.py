import logging
import os
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
sql_sections = {
    "snowflake_setup": "Setting up the dbt User and Roles",
    "snowflake_import": "Importing Raw Tables",
    "capstone_airstats": "Importing AIRSTATS Capstone Tables",
}


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


@st.cache_data
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
# 🚀 dbt (Data Build Tool) Bootcamp
## ❄️ Snowflake and Profile Setup Helper

Hi there! 👋

This webapp helps you getting started with dbt, Snowflake and Preset, the BI tool we'll use in the course.

**We'll do the following**:

* **Step 1)** Key Generation - Snowflake requires a key-based authentication, we'll generate a keypair for you that you can use then to connect to Snowflake.
* **Step 2)** Snowflake Setup - We'll set up your Snowflake account and import the raw AirBnB tables.
* **Step 3)** Configuration Files - We'll download the configuration files needed for your dbt project and Preset.

On with the setup! 🎉
"""

hello_msg_ceu = """
# 🎓 CEU Modern Data Platforms
## ❄️ Snowflake and Profile Setup Helper

Hi there! 👋

This webapp helps you getting started with dbt, Snowflake and Preset for the **CEU Modern Data Platforms** course.

**We'll do the following**:

* **Step 1)** Key Generation - Snowflake requires a key-based authentication, we'll generate a keypair for you that you can use then to connect to Snowflake.
* **Step 2)** Snowflake Setup - We'll set up your Snowflake account and import the raw AirBnB tables **and the AIRSTATS capstone database**.
* **Step 3)** Configuration Files - We'll download the configuration files needed for your dbt project and Preset.

On with the setup! 🎉
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
    return f"commit: {commit_link} | started: {APP_START_TIME} UTC"


def main():
    session_id = streamlit_session_id()
    logger.info("Starting Streamlit app")

    # Detect course mode from query params
    course_mode = st.query_params.get("course", "default")
    if "course_mode" not in st.session_state:
        st.session_state.course_mode = course_mode
    is_ceu_mode = st.session_state.course_mode == "ceu"

    # Initialize session state for step tracking
    if "step" not in st.session_state:
        st.session_state.step = 0

    # Landing Page
    if st.session_state.step == 0:
        hello_msg = hello_msg_ceu if is_ceu_mode else hello_msg_default
        st.markdown(hello_msg)

        if st.button(
            "🚀 Start Setup Process",
            type="primary",
            use_container_width=True,
            key="btn_start_setup",
        ):
            st.session_state.step = 1
            st.rerun()

    # Step 1: Keypair Generation
    elif st.session_state.step == 1:
        st.markdown("### 🔐 Step 1: Generate Snowflake Access Keys")

        if st.button("⬅️ Back to Welcome", type="secondary", key="btn_back_to_welcome"):
            st.session_state.step = 0
            st.rerun()

        if "keypair" not in st.session_state:
            with st.status("Generating keypair..."):
                st.session_state.keypair = generate_keys("q")
                st.markdown(" ✅ Private Key (rsa_key.p8)")
                st.markdown(" ✅ Public Key (rsa_key.pub)")
        keypair = st.session_state.keypair
        st.info(
            "Keypair files generated successfully!\n\n💾 Save these two files below and keep them safe and accessible for later. Then, click the button below to continue to the Snowflake Setup."
        )

        st.download_button(
            label="🔑 Download Private Key (rsa_key.p8)",
            data=keypair.private_key,
            file_name="rsa_key.p8",
            mime="text/plain",
            key="btn_download_private_key",
        )

        st.download_button(
            label="🔐 Download Public Key (rsa_key.pub)",
            data=keypair.public_key,
            file_name="rsa_key.pub",
            mime="text/plain",
            key="btn_download_public_key",
        )

        if st.button(
            "➡️ Continue to Snowflake Setup", type="primary", key="btn_continue_to_snowflake"
        ):
            st.session_state.step = 2
            st.rerun()

    # Step 2: Snowflake Setup (original functionality)
    elif st.session_state.step == 2:
        snowflake_setup_complete = False
        st.markdown("### ✅ Step 1: Generate Snowflake Access Keys - Completed")
        st.markdown("### ❄️ Step 2: Snowflake Setup")

        # Add back button
        if st.button(
            "⬅️ Back to Access Keys Generation", key="btn_back_to_keys"
        ):
            st.session_state.step = 1
            st.rerun()

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
            key="input_snowflake_account",
        )
        hostname = extract_snowflake_account(hostname_raw)

        # Check if the account format is valid
        account_is_valid = is_valid_snowflake_account(hostname)

        # Store the account in session state for later use
        st.session_state.snowflake_account = hostname

        if hostname_raw.strip() != "xxxxxx-xxxxxxxx" and not account_is_valid:
            st.warning(
                "⚠️ This doesn't look like a valid Snowflake account format. Please check your account identifier."
            )
        else:
            # Show the extracted account identifier if it's different from the input
            if hostname != hostname_raw and hostname_raw.strip() != "xxxxxx-xxxxxxxx":
                st.info(f"Using account identifier: `{hostname}`")
        username = st.text_input(
            "Snowflake username (change this is you didn't set it to `admin` at registration):",
            env_username,
            key="input_snowflake_username",
        )
        password = st.text_input(
            "Snowflake Password:",
            env_password,
            type="password",
            key="input_snowflake_password",
        )

        st.warning(
            "Snowflake has been rolling out an update gradually which enforces **Multi Factor Authentication (MFA)**. If you have been enrolled to MFA, a push notification will be sent to your DUO app after you click _Start Setup_. If this happens, please approve the request and the setup will continue automatically.\n\n"
            "**If you use TOTP-based MFA** (Google/Microsoft Authenticator, or Duo TOTP), check the box below and enter your 6-digit code."
        )

        use_totp = st.checkbox(
            "I use TOTP-based MFA (authenticator app that generates 6-digit codes)",
            key="checkbox_use_totp",
            help="Check this if you use an authenticator app like Google Authenticator, Microsoft Authenticator, or Duo TOTP"
        )

        passcode = None
        if use_totp:
            passcode = st.text_input(
                "Enter your 6-digit TOTP code:",
                max_chars=6,
                key="input_totp_passcode",
                help="Open your authenticator app and enter the current 6-digit code for Snowflake"
            )

        if st.button("🎯 Start Setup", key="btn_start_snowflake_setup"):
            if len(password) == 0:
                st.error("🚨 Please provide a password")
                return

            # Load and process SQL commands with public key substitution
            with open(CURRENT_DIR + "/course-resources.md", "r") as file:
                md = file.read().rstrip()
            # Get the public key from session state if available
            public_key = st.session_state.keypair.public_key
            sql_commands = get_sql_commands(md, public_key)

            # Load capstone SQL if in CEU mode
            if is_ceu_mode:
                capstone_path = CURRENT_DIR + "/capstone-resources.md"
                if os.path.exists(capstone_path):
                    with open(capstone_path, "r") as file:
                        capstone_md = file.read().rstrip()
                    capstone_commands = get_sql_commands(capstone_md, public_key)
                    sql_commands.update(capstone_commands)

            print(sql_commands)

            try:
                with st.status("🔌 Connecting to Snowflake"):
                    connection_cm = get_snowflake_connection(hostname, username, password, passcode)
                    connection = connection_cm.__enter__()
            except InterfaceError as e:
                st.error(
                    f"""Error connecting to Snowflake. This usually means that the snowflake account is invalid.
                    Please verify the snowflake account and try again.\n\nOriginal Error: \n\n{e.orig}"""
                )
                logging.warning(
                    f"{session_id}: Error connecting to Snowflake. Account: {hostname}, Username: {username}: {e}"
                )
                return
            except DatabaseError as e:
                print(e)
                error_str = str(e.orig) if hasattr(e, 'orig') else str(e)

                # Check if this is a TOTP MFA error
                if "TOTP is required" in error_str or "MFA with TOTP" in error_str:
                    st.error(
                        "🔐 **Your Snowflake account requires TOTP-based MFA.**\n\n"
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
                return
            except Exception as e:

                st.error(
                    f"Error connecting to Snowflake.\n\nOriginal Error:\n\n{e}\n\nStacktrace:\n\n{traceback.format_exc()}"
                )
                logging.warning(
                    f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}\nStacktrace:\n{traceback.format_exc()}"
                )
                return

            try:
                with st.status(
                    f"⚙️ Setting up your Snowflake account (this can take up to 2 minutes)"
                ) as status_spinner:
                    try:
                        for section, commands in sql_commands.items():
                            # Skip capstone section if not in CEU mode
                            if section == "capstone_airstats" and not is_ceu_mode:
                                continue
                            with st.status(
                                sql_sections[section]
                            ) as internal_status_spinner:
                                for command in commands:
                                    st.write(f"Executing command: `{command}`")
                                    connection.execute(text(command))
                                    connection.commit()

                        # Verify AIRBNB tables (use fully qualified names in case context changed)
                        tables_to_verify = [
                            "AIRBNB.RAW.RAW_LISTINGS",
                            "AIRBNB.RAW.RAW_HOSTS",
                            "AIRBNB.RAW.RAW_REVIEWS",
                        ]
                        for table in tables_to_verify:
                            result = connection.execute(
                                text(f"SELECT COUNT(*) FROM {table}")
                            )
                            count = result.fetchone()[0]
                            if count == 0:
                                st.error(
                                    f"Table {table} has no rows. This is unexpected. Please check the logs and try again."
                                )
                                return

                        # Verify AIRSTATS tables if in CEU mode
                        if is_ceu_mode:
                            airstats_tables = [
                                "AIRSTATS.RAW.AIRPORTS",
                                "AIRSTATS.RAW.AIRPORT_COMMENTS",
                                "AIRSTATS.RAW.RUNWAYS",
                            ]
                            for table in airstats_tables:
                                result = connection.execute(
                                    text(f"SELECT COUNT(*) FROM {table}")
                                )
                                count = result.fetchone()[0]
                                if count == 0:
                                    st.error(
                                        f"Table {table} has no rows. This is unexpected. Please check the logs and try again."
                                    )
                                    return

                    except Exception as e:
                        st.error(
                            f"Error executing command {command}.\n\nOriginal Error:\n\n{e}\n\nTraceback:\n\n{traceback.format_exc()}"
                        )
                        logging.warning(
                            f"{session_id}: Error executing command {command}. Account name: {hostname}\n Original Error: {e}"
                        )
                        internal_status_spinner.update(
                            label="Error executing command",
                            state="error",
                            expanded=True,
                        )
                        status_spinner.update(
                            label="Error executing command",
                            state="error",
                            expanded=True,
                        )
                        return

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
                                    dbt_result = dbt_connection.execute(
                                        text(f"USE ROLE {users[1]}")
                                    )
                                    dbt_result = dbt_connection.execute(
                                        text(f"USE DATABASE AIRBNB")
                                    )
                                    dbt_result = dbt_connection.execute(
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
                        snowflake_setup_complete = True

                    except Exception as e:
                        error_msg = (
                            f"❌ Failed to connect with {users[0]} user or query "
                            f"RAW_LISTINGS: {str(e)}"
                        )
                        st.error(error_msg)
                        st.warning(
                            "This might indicate an issue with the {users[0]} user "
                            "setup or permissions."
                        )
                        logging.warning(
                            f"{session_id}: {users[0]} user connection failed: {e}\nTraceback:\n{traceback.format_exc()}"
                        )
                        internal_status_spinner.update(
                            label=f"Error Connecting as {users[0]} user",
                            state="error",
                            expanded=True,
                        )
                        status_spinner.update(
                            label=f"Error Connecting as {users[0]} user",
                            state="error",
                            expanded=True,
                        )
            finally:
                # Ensure the main Snowflake connection is always cleaned up
                connection_cm.__exit__(None, None, None)

        if snowflake_setup_complete:
            success_msg = "🎉 Snowflake Setup complete! Let's continue with downloading the configuration files!"
            st.toast(success_msg, icon="🔥")
            status_spinner.success(success_msg, icon="🔥")

            st.session_state.step = 3
            if st.button(
                "📥 Download Configuration Files",
                type="primary",
                key="btn_goto_downloads",
            ):
                st.rerun()

    # Step 3: Download Configuration Files
    elif st.session_state.step == 3:
        st.markdown("### ✅ Step 1: Generate Snowflake Access Keys - Completed")
        st.markdown("### ✅ Step 2: Snowflake Setup - Completed")
        st.markdown("### 📄 Step 3: Download Configuration Files")

        # Add back button
        if st.button(
            "⬅️ Back to Snowflake Setup", type="secondary", key="btn_back_to_snowflake"
        ):
            st.session_state.step = 2
            st.rerun()

        st.markdown(
            """Download the configuration files needed for dbt and Preset integration.

 * `profiles.yml`: contains your dbt connection configuration which you'll need to copy to your dbt project folder later.
 * `preset-instructions.md`: contains instructions for connecting to Preset, which we'll cover later in the course."""
        )

        # Get the keypair and account info from session state
        if "keypair" not in st.session_state:
            st.error("🚨 No keypair found. Please go back and generate keys first.")
            return

        if "snowflake_account" not in st.session_state:
            st.error(
                "🚨 No Snowflake account found. Please go back and complete "
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
            st.markdown("#### 🛠️ dbt profiles.yml")
            st.markdown("This file contains your dbt connection configuration.")
            st.download_button(
                label="📥 Download profiles.yml",
                data=profiles_content,
                file_name="profiles.yml",
                mime="text/yaml",
                key="btn_download_profiles",
            )

        with col2:
            st.markdown("#### 📋 Preset Instructions")
            st.markdown("This file contains instructions for connecting to Preset.")
            st.download_button(
                label="📥 Download preset-instructions.md",
                data=preset_content,
                file_name="preset-instructions.md",
                mime="text/markdown",
                key="btn_download_preset",
            )

        st.success("🎉 Configuration files ready for download!")
        st.info(
            "🎯 You can now use these files to configure dbt and Preset with "
            "your Snowflake database."
        )

        st.toast("Configuration files ready for download!", icon="🔥")
        st.success(
            "🎓 Once you downloaded the files, you can go back to the course and continue with the setup!"
        )

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
