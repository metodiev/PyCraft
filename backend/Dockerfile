# PyCraft API image.
#
# Build:  docker build -t pycraft-api -f backend/Dockerfile backend/
#
# Note: the API does NOT execute user code — it dispatches sandbox containers
# to the Docker daemon. See docs/security-model.md.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so application edits do not invalidate the pip layer.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir .

# Challenges are mounted at run time (see docker-compose.yml); this is a
# fallback so the image is self-contained.
COPY --chown=1000:1000 . /app

RUN useradd --uid 1000 --no-create-home --shell /usr/sbin/nologin pycraft \
    && chown -R 1000:1000 /app
USER 1000:1000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
