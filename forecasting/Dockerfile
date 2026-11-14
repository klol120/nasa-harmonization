FROM ghcr.io/astral-sh/uv:0.13.6 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN --mount=type=secret,id=build_ca_bundle \
    if [ -s /run/secrets/build_ca_bundle ]; then \
      SSL_CERT_FILE=/run/secrets/build_ca_bundle uv --no-cache --system-certs sync --frozen --no-dev --no-editable; \
    else uv --no-cache --system-certs sync --frozen --no-dev --no-editable; fi \
    && useradd --uid 10001 --create-home firecast
USER 10001
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 MPLCONFIGDIR=/tmp/matplotlib
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz',timeout=3)"
CMD ["uvicorn", "firecast.service:app", "--host", "0.0.0.0", "--port", "8000"]
