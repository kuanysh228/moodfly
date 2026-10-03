FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    NUMBA_CACHE_DIR=/app/data/numba-cache \
    MOODFLY_HOST=0.0.0.0 \
    MOODFLY_PORT=8000 \
    PATH="/app/backend/.venv/bin:$PATH"

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend ./
RUN uv sync --frozen --no-dev

WORKDIR /app
COPY frontend frontend
COPY scripts scripts
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

VOLUME /app/data
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
