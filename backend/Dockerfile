FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.29 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --group ml --no-install-project

COPY firecal_api ./firecal_api
COPY README.md ./
RUN uv sync --frozen --no-dev --group ml

COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "firecal_api.cli", "serve", "--host", "0.0.0.0", "--port", "8000"]
