from logging import getLogger
import argparse
import os
import re

from sqlalchemy import text
from sqlalchemy.exc import InterfaceError, DatabaseError
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.dialects import registry
import logging
from collections import OrderedDict


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sql_sections = {
    "snowflake_setup": "Setting up the dbt User an Roles",
    "snowflake_import": "Importing Raw Tables",
    "snowflake_reporter": "Creating Reporter Role"
}


def get_snowflake_connection(account, username, password):

    engine = create_engine(
        f"snowflake://{username}:{password}@{account}/AIRBNB/DEV?warehouse=COMPUTE_WH&role=ACCOUNTADMIN&account_identifier={account}"
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
    return {k: [c.strip("\n") for c in v.split(";") if c.strip() != ""] for k, v in commands.items()}


hello_msg = """
# dbt Zero to Hero Snowflake Importer (beta)

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
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')


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
    hostname = st.text_input(
        "Snowflake account (this looks like as `frgcsyo-ie17820` or `frgcsyo-ie17820.aws`, check your snowlake registration email).\n\n_**This is not your Snowflake username**, but the first part of the snowflake url you received in your snowflake registration email_:",
        "jdehewj-vmb00970")
    username = st.text_input(
        "Snowflake username (change this is you didn't set it to `admin` at registration):", "admin")
    password = st.text_input(
        "Snowflake Password:", pw, type="password")

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
                Please verify the snowflake account and try again.\n\nOriginal Error: \n\n{e.orig}""")
            logging.warning(
                f"{session_id}: Error connecting to Snowflake. Account: {hostname}, Username: {username}: {e}")
            return
        except DatabaseError as e:
            print(e)
            st.error(
                f"Error connecting to Snowflake. This usually means that the snowflake username or password you provided is not valid. Please correct them and retry by pressing the Start Setup button.\n\nOriginal Error:\n\n{e.orig}")
            logging.warning(
                f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}")
            return
        except Exception as e:
            st.error(
                f"Error connecting to Snowflake.\n\nOriginal Error:\n\n{e.orig}")
            logging.warning(
                f"{session_id}: Error connecting to Snowflake. Account name: {hostname}\n Original Error: {e}")
            return

        st.success("Connected to Snowflake successfully!")
        try:
            for section, commands in sql_commands.items():
                with st.status(sql_sections[section]):
                    for command in commands:
                        if command.startswith("GRANT USAGE ON SCHEMA AIRBNB.DEV TO ROLE REPORTER"):
                            command = "GRANT USAGE ON FUTURE SCHEMAS IN DATABASE AIRBNB TO ROLE REPORTER;"
                            st.write(f"Patching Reporter command: `{command}`")
                        else:
                            st.write(f"Executing command: `{command}`")
                        connection.execute(text(command))
            st.toast("Setup complete! You can now go back to the course!", icon="🔥")
            st.success(
                "Setup complete! You can now go back to the course!", icon="🔥")
        except Exception as e:
            st.error(
                f"Error executing command {command}.\n\nOriginal Error:\n\n{e.orig}")
            logging.warning(
                f"{session_id}: Error executing command {command}. Account name: {hostname}\n Original Error: {e}")
            return


if __name__ == "__main__":
    print("Starting Streamlit app")
    main()
