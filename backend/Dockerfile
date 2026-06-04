# Backend image. Runs the FastAPI app via uv. Build from the repo root:
#   docker build -f backend/Dockerfile -t change-court .
FROM python:3.11-slim

# uv provides the toolchain; copy its static binaries from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./

# Run as an unprivileged user; own /app so the venv, the SQLite DB, and checkpoints stay writable.
RUN adduser --disabled-password --gecos "" --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
# Serve the deployment ASGI app: REST health PLUS the OAuth2-protected MCP server at /mcp.
# (app.main:app is health-only and would leave the declarative agent without its MCP endpoint.)
CMD ["uv", "run", "--no-dev", "uvicorn", "app.asgi:app", "--host", "0.0.0.0", "--port", "8000"]
