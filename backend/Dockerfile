# Backend image. Runs the FastAPI app via uv. Build from the repo root:
#   docker build -f backend/Dockerfile -t change-court .
FROM python:3.11-slim

# uv provides the toolchain; copy its static binaries from the official image.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./

EXPOSE 8000
CMD ["uv", "run", "--no-dev", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
