# dbt Snowflake Setup Helper

A Streamlit app to help set up Snowflake accounts and import course resources for the dbt bootcamp.

## Quick Start

### Local Development
```bash
# Option 1: Direct streamlit command
streamlit run

# Option 2: Using the runner script
python run.py

# Option 3: Specify the file explicitly
streamlit run streamlit_app.py
```

### Streamlit Cloud Deployment
1. Push this repository to GitHub
2. Connect to Streamlit Cloud
3. The app will automatically detect `streamlit_app.py` and deploy

## Features

- **Step 1:** Automatic RSA keypair generation and download
- **Step 2:** Snowflake account setup and data import
- **Security:** Encrypted private keys with passphrase protection
- **User-friendly:** Step-by-step guided process

## Configuration

The app uses `.streamlit/config.toml` for configuration:
- Auto-reload on file changes (`runOnSave = true`)
- Streamlit Cloud compatible settings
- Custom theme (optional)

## Requirements

See `requirements.txt` for all dependencies. Key packages:
- streamlit
- cryptography (for key generation)
- sqlalchemy (for Snowflake connection)
- snowflake-sqlalchemy