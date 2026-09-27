# PyCraft Python execution image.
#
# Build:  docker build -t pycraft-runner:3.12 -f runner/Dockerfile runner/
#
# The image is deliberately minimal: CPython plus pytest, no network tools, no
# compilers. Hardening is applied at run time by the execution backend via
# --network=none, --read-only, --cap-drop=ALL, --pids-limit, --memory and
# --user; the image itself only has to be small and predictable.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# pytest is the only third-party runtime dependency of a challenge.
RUN pip install --no-cache-dir "pytest==8.3.4" "pytest-asyncio==0.24.0"

# Unprivileged account; the execution backend also passes --user explicitly so
# the container never runs as root even if that flag is dropped.
RUN groupadd --gid 1000 runner \
    && useradd --uid 1000 --gid 1000 --no-create-home --shell /usr/sbin/nologin runner

WORKDIR /opt/pycraft
COPY entrypoint.py pycraft_report.py ./

# Read-only payload mount point. The entrypoint copies from here into a
# writable scratch directory because the container root filesystem is read-only.
RUN mkdir -p /opt/payload && chmod -R a-w /opt/pycraft

USER 1000:1000

# The entrypoint prints a single JSON document delimited by markers on stdout.
ENTRYPOINT ["python", "-I", "-B", "/opt/pycraft/entrypoint.py"]
