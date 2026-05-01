# Backend image — runs FastAPI via uvicorn.
# Uses uv to install deps from pyproject.toml + uv.lock for reproducible builds.

FROM python:3.12-slim

# System packages: build essentials for any wheel that needs compiling, plus
# libpq for SQLAlchemy/asyncpg, and curl for healthchecks.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv (the package manager we use locally too).
RUN pip install --no-cache-dir uv

WORKDIR /app

# Copy lockfile + manifest first so Docker can cache the dep install layer.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Now copy the actual source code.
COPY . .

# Tell Python to find packages from /app.
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# Run migrations on startup, then launch the API.
# We use the venv that uv created at /app/.venv.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000"]