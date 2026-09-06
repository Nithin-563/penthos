# Base Python sandbox image for Penthos.
#
# ARM64-compatible, minimal, non-root. Contains only the Python runtime and
# a small set of testing utilities. No network access is provided at
# execution time; dependency installation is a separate, later concern.
#
# Build:
#   docker build -f sandbox/images/python.Dockerfile -t penthos-sandbox:python sandbox

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN useradd --create-home --shell /bin/sh --uid 1000 sandbox \
    && mkdir -p /workspace \
    && chown sandbox:sandbox /workspace

# A deliberately tiny test/dependency set installable without network at
# build time only. Kept minimal so the image stays small.
RUN pip install --no-cache-dir pytest==8.3.4

WORKDIR /workspace

USER sandbox
