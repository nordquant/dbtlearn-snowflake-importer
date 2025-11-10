# dbt Bootcamp Setup - Snowflake Importer

A Streamlit web application that automates Snowflake account setup for the dbt Zero to Hero Udemy course. This app helps students quickly configure their Snowflake environment with the necessary databases, users, roles, and sample data.

**Now with zero-downtime deployments!**

## Features

- 🚀 Automated Snowflake account setup
- 👤 Creates dbt user with appropriate roles and permissions
- 🗄️ Sets up AIRBNB database with RAW and DEV schemas
- 📊 Imports sample AirBnB data from S3
- ✅ Validates data import with row count checks
- 🎯 Creates REPORTER role for dashboard access

## Quick Start

### Running Locally with Python

```bash
# Install dependencies (requires Python 3.13)
uv sync

# Run the Streamlit app
uv run streamlit run streamlit_app.py
```

### Running with Docker

```bash
# Using docker-compose (easiest)
docker-compose up -d

# Or pull from registry
docker run -p 8501:8501 registry.nordquant.com/dbt-bootcamp-setup:latest
```

Access the app at http://localhost:8501

## Development

### Prerequisites

- Python 3.13
- [uv](https://github.com/astral-sh/uv) package manager
- Docker (for containerized deployment)

### Setup

```bash
# Install dependencies
uv sync

# Install dev dependencies
uv sync --extra dev

# Run tests
docker-compose --profile test up test --exit-code-from test
```

### Project Structure

```
.
├── streamlit_app.py          # Main Streamlit application
├── course-resources.md       # SQL setup commands (from course)
├── pyproject.toml           # Python dependencies (uv format)
├── Dockerfile               # Multi-stage Docker build
├── docker-compose.yml       # Docker compose with test profile
├── build_push.sh           # Build script for multi-platform images
└── DOCKER.md               # Docker documentation
```

## Docker

This project uses a multi-stage Docker build optimized for caching:

- **Base**: Python 3.13 Alpine with build tools
- **Dependencies**: Python packages (cached when dependencies unchanged)
- **Final**: Application code (rebuilt on code changes)

### Building and Pushing

```bash
# Build and push for both amd64 and arm64
./build_push.sh

# Build only (no push)
./build_push.sh --build-only --platform linux/arm64

# Custom tag
./build_push.sh --tag v1.0.0

# See all options
./build_push.sh --help
```

See [DOCKER.md](DOCKER.md) for detailed Docker documentation.

## Configuration

The app creates the following Snowflake resources:

- **User**: `dbt` (password: `dbtPassword123`)
- **Roles**: `TRANSFORM`, `REPORTER`
- **Database**: `AIRBNB`
- **Schemas**: `RAW`, `DEV`
- **Tables**: `raw_listings`, `raw_hosts`, `raw_reviews`

## Deployment

### GitHub Actions

The project includes a CI/CD pipeline that:
1. Builds Docker images for amd64 and arm64
2. Runs health checks and integration tests
3. Pushes to `registry.nordquant.com/dbt-bootcamp-setup:latest`

Required GitHub secrets:
- `REGISTRY_USERNAME`
- `REGISTRY_PASSWORD`

See [.github/workflows/build-and-push.yml](.github/workflows/build-and-push.yml) for details.

## Dependencies

Main dependencies (pinned to major.minor versions):
- `streamlit>=1.51,<1.52` - Web application framework
- `sqlalchemy>=2.0,<2.1` - Database ORM
- `snowflake-sqlalchemy>=1.7,<1.8` - Snowflake dialect
- `snowflake-connector-python>=3.18,<3.19` - Snowflake driver
- `pydantic>=2.12,<2.13` - Data validation
- `urllib3>=2.5,<2.6` - HTTP client (required for Python 3.13)

See [pyproject.toml](pyproject.toml) for full dependency list.

## License

This project is part of the dbt Zero to Hero Udemy course materials.

## Support

For issues or questions about:
- **The application**: Check the logs in the Streamlit interface
- **Docker deployment**: See [DOCKER.md](DOCKER.md)
- **The dbt course**: Refer to the Udemy course materials# Test change for manual workflow trigger
