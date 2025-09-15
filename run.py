#!/usr/bin/env python3
"""
Simple runner script for the Streamlit app.
This allows running with: python run.py
"""

import subprocess
import sys

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "streamlit", "run", "streamlit_app.py"])
