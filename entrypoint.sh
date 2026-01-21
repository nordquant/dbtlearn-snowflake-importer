#!/bin/sh
# Entrypoint script for dbt-bootcamp-setup container

# Create static directory and generate container info JSON
# This must happen before Streamlit starts so static file serving works
mkdir -p /app/static

cat > /app/static/container-info.json << EOF
{
  "container_id": "${HOSTNAME}",
  "git_commit": "${GIT_COMMIT:-unknown}",
  "started_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

echo "Container info: $(cat /app/static/container-info.json)"

# Start Streamlit
exec /app/.venv/bin/streamlit run streamlit_app.py \
    --server.address 0.0.0.0 \
    --server.port 8501 \
    --server.headless true