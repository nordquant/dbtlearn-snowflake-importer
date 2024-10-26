# %%

# pip install sqlalchemy snowflake-sqlalchemy markdown pyyaml

import argparse
import os
import re

from sqlalchemy import text
import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.dialects import registry
import logging

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_snowflake_connection(account, username, password):

    engine = create_engine(
        f"snowflake://{username}:{password}@{
            account}/AIRBNB/DEV?warehouse=COMPUTE_WH&role=ACCOUNTADMIN&account_identifier={account}"
    )
    connection = engine.connect()

    return connection


def get_sql_commands(md):
    in_named_sql = False
    commands_only = ""
    for l in md.split("\n"):
        if in_named_sql:
            if l.startswith("```"):
                in_named_sql = False
            else:
                if l.strip() == "" or l.startswith("--"):
                    continue
                commands_only += l + "\n"
        elif l.startswith("```sql {#"):
            in_named_sql = True
    return [c for c in commands_only.split(";") if c.strip() != ""]


hello_msg = """
# dbt Zero to Hero Snowflake Importer

Hi, this webapp helps you set up your Snowflake account
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


def main():
    print("Starting Streamlit app")
    registry.register("snowflake", "snowflake.sqlalchemy", "dialect")
    pw = (
        os.environ.get("SNOWFLAKE_PASSWORD")
        if os.environ.get("SNOWFLAKE_PASSWORD")
        else ""
    )
    st.markdown(hello_msg)
    hostname = st.text_input(
        "Snowflake account name (this looks like as `frgcsyo-ie17820` or `frgcsyo-ie17820.aws`, check your snowlake registration email). _This is not your username, but the first part of the snowflake url you received in your snowflake registration email_:", "")
    username = st.text_input(
        "Snowflake username (change this is you didn't set it to `admin` at registration):", "admin")
    password = st.text_input("Snowflake Password (it will be visible!):", pw)
    if st.button("Start Setup"):

        with open(CURRENT_DIR + "/course-resources.md", "r") as file:
            md = file.read().rstrip()

        try:
            with st.status("Connecting to Snowflake"):
                connection = get_snowflake_connection(
                    hostname, username, password)
        except Exception as e:
            st.error(
                f"Error connecting to Snowflake. This usually means that the snowflake account name, username or password you provided is not valid. Please correct the account name and retry by pressing the Start Setup button.\n\nOriginal Error:\n\n{e}")
            logging.warning(f"Error connecting to Snowflake. Account name: {
                            hostname}\n Original Error: {e}")
            return

        with st.status("Setting up your Snowflake environment"):
            sql_commands = get_sql_commands(md)
            for command in sql_commands:
                st.write(f"Executing command: `{command}`")
                connection.execute(text(command))
        st.toast("Setup complete! You can now go back to the course!", icon="🔥")


if __name__ == "__main__":
    print("Starting Streamlit app")
    main()
