#!/usr/bin/env bash
python -m streamlit run snowflake_manager.py --server.runOnSave true  --server.enableCORS false --server.enableXsrfProtection false --server.address 0.0.0.0