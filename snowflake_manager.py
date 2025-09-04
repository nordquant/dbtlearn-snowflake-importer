import logging
import os
import re
from collections import OrderedDict
from logging import getLogger
from urllib.parse import quote_plus

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.dialects import registry
from sqlalchemy.exc import DatabaseError, InterfaceError

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sql_sections = {
    "snowflake_setup": "Setting up the dbt User an Roles",
    "snowflake_import": "Importing Raw Tables",
    "snowflake_reporter": "Creating Reporter Role",
}


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
    
    # Extract from URL if it's a full URL
    url_match = re.search(r'https?://([^/]+)', input_text)
    if url_match:
        input_text = url_match.group(1)
    
    # Remove .snowflakecomputing.com suffix if present
    input_text = re.sub(r'\.snowflakecomputing\.com.*$', '', input_text)
    
    # Extract the account identifier pattern
    # Matches: word-word, word-word.aws, word.aws, or just word
    account_match = re.match(r'^([a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)?(?:\.aws)?)(?:\..*)?$', input_text)
    
    if account_match:
        return account_match.group(1)
    
    # If no pattern matches, return original input (fallback)
    return raw_input


def get_snowflake_connection(account, username, password):
    # URL encode the username and password to handle special characters
    encoded_username = quote_plus(username)
    encoded_password = quote_plus(password)

    engine = create_engine(
        f"snowflake://{encoded_username}:{encoded_password}@{account}/AIRBNB/DEV?warehouse=COMPUTE_WH&role=ACCOUNTADMIN&account_identifier={account}"
    )
    connection = engine.connect()

    return connection


def streamlit_session_id():
    from streamlit.runtime import get_instance
    from streamlit.runtime.scriptrunner import get_script_run_ctx

    runtime = get_instance()
    session_id = get_script_run_ctx().session_id
    session_info = runtime._session_mgr.get_session_info(session_id)
    if session_info is None:
        return "nosession"
    return session_info.session.id


def get_sql_commands(md):
    commands = OrderedDict()
    current_section = None
    in_named_sql = False
    commands_only = ""
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
                commands[current_section] += l + "\n"
        elif l.startswith("```sql {#"):
            in_named_sql = True
            current_section = l.split("{#")[1].split("}")[0]
    return {
        k: [c.strip("\n") for c in v.split(";") if c.strip() != ""]
        for k, v in commands.items()
    }


hello_msg = """
# dbt Zero to Hero Snowflake Importer

Hi,

this webapp helps you set up your Snowflake account
and import the course resources, such as raw tables and user roles
into your Snowflake account. Simply add the snowflake hostname, username and password
and then click start setup.

**This app will do the following**:

* Create the `dbt` user using the password `dbtPassword123`
* Import the raw AirBnB tables
* Create the REPORTER role and grant it to the `dbt` user. _We'll use this role later in the course when we build a dashboard.

Please keep in mind that this is a beta version implemented in late October 2024 and it may have some rought edges.
I'd be very happy if you could provide feedback on wether the tool works and how to improve it. Just send me a message on Udemy.

"""


logging.root.setLevel(logging.INFO)
logger = getLogger(__name__)
logger.Formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)


def main():
    session_id = streamlit_session_id()
    logger.info("Starting Streamlit app")
    with open(CURRENT_DIR + "/course-resources.md", "r") as file:
        md = file.read().rstrip()
        sql_commands = get_sql_commands(md)
        print(sql_commands)

    registry.register("snowflake", "snowflake.sqlalchemy", "dialect")
    pw = (
        os.environ.get("SNOWFLAKE_PASSWORD")
        if os.environ.get("SNOWFLAKE_PASSWORD")
        else ""
    )
    st.markdown(hello_msg)
    hostname_raw = st.text_input(
        "Snowflake account (this looks like as `frgcsyo-ie17820` or `frgcsyo-ie17820.aws`, check your snowlake registration email).\n\n_**This is not your Snowflake username**, but the first part of the snowflake url you received in your snowflake registration email_:",
        "xxxxxx-xxxxxxxx",
    )
    hostname = extract_snowflake_account(hostname_raw)
    
    # Show the extracted account identifier if it's different from the input
    if hostname != hostname_raw and hostname_raw.strip() != "xxxxxx-xxxxxxxx":
        st.info(f"Using account identifier: `{hostname}`")
    username = st.text_input(
        "Snowflake username (change this is you didn't set it to `admin` at registration):",
        "admin",
    )
    password = st.text_input("Snowflake Password:", pw, type="password")

    st.warning("Snowflake has been rolling out an update gradually which enforces **Multi Factor Authentication (MFA)**. If you have been enrolled to MFA, a text message / push notification will be sent to your DUO Authenticator app after you click _Start Setup_. If this happens, please approve the request and the setup will continue automatically.")
    if st.button("Start Setup"):
        if len(password) == 0:
            st.error("Please provide a password")
            return
        try:
            with st.status("Connecting to Snowflake"):
                connection = get_snowflake_connection(
                    hostname, username, password)
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
            st.error(
                f"Error connecting to Snowflake. This usually means that the snowflake username or password you provided is not valid. Please correct them and retry by pressing the Start Setup button.\n\nOriginal Error:\n\n{e.orig}"
            )
            logging.warning(
                f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}"
            )
            return
        except Exception as e:
            st.error(
                f"Error connecting to Snowflake.\n\nOriginal Error:\n\n{e.orig}")
            logging.warning(
                f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}"
            )
            return

        st.success("Connected to Snowflake successfully!")
        try:
            for section, commands in sql_commands.items():
                with st.status(sql_sections[section]):
                    for command in commands:
                        if command.startswith(
                            "GRANT USAGE ON SCHEMA AIRBNB.DEV TO ROLE REPORTER"
                        ):
                            command = "GRANT USAGE ON FUTURE SCHEMAS IN DATABASE AIRBNB TO ROLE REPORTER;"
                            st.write(f"Patching Reporter command: `{command}`")
                        else:
                            st.write(f"Executing command: `{command}`")
                        connection.execute(text(command))
                        connection.commit()
            for table in ["RAW_LISTINGS", "RAW_HOSTS", "RAW_REVIEWS"]:
                with st.status(
                    f"Checking if data was imported for table {table} correctly"
                ):
                    result = connection.execute(
                        text(f"SELECT COUNT(*) FROM {table}"))
                    count = result.fetchone()[0]
                    st.write(f"Table {table} has {count} rows")
                    if count == 0:
                        st.error(
                            f"Table {table} has no rows. This is unexpected. Please check the logs and try again."
                        )
                        return
            st.toast("Setup complete! You can now go back to the course!", icon="🔥")
            st.success(
                "Setup complete! You can now go back to the course!", icon="🔥")
        except Exception as e:
            st.error(
                f"Error executing command {command}.\n\nOriginal Error:\n\n{e.orig}"
            )
            logging.warning(
                f"{session_id}: Error executing command {command}. Account name: {hostname}\n Original Error: {e}"
            )
            return


if __name__ == "__main__":
    print("Starting Streamlit app")
    main()
