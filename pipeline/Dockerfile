# The firecal pipeline as a container, used for the world batch on Azure (tools/world_batch.py).
# data/ is a mounted volume; nothing under it is baked into the image.
FROM python:3.12-slim

# firecal runs from /app/src (not installed): config.py finds config.yaml relative to its own file.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONPATH=/app/src
WORKDIR /app

# Dependencies only (from pyproject.toml), first, so code changes don't reinstall them.
COPY pyproject.toml ./
RUN mkdir -p src/firecal && touch src/firecal/__init__.py \
    && pip install . && pip uninstall -y firecal && rm -rf build src *.egg-info

COPY src ./src
COPY tools ./tools
COPY config.yaml ./
COPY config.d ./config.d
COPY docs ./docs

CMD ["python", "tools/world_batch.py"]
