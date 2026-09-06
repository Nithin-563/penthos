# Base Node.js sandbox image for Penthos.
#
# ARM64-compatible, minimal, non-root. Contains only the Node runtime and
# npm/npx. No network access is provided at execution time.
#
# Build:
#   docker build -f sandbox/images/node.Dockerfile -t penthos-sandbox:node sandbox

FROM node:20-bookworm-slim

ENV NPM_CONFIG_CACHE=/tmp/npm-cache \
    NODE_ENV=production

# The official Node image ships a 'node' user at UID 1000, so the sandbox
# user uses UID 1001 here to avoid a collision.
RUN useradd --create-home --shell /bin/sh --uid 1001 sandbox \
    && mkdir -p /workspace /tmp/npm-cache \
    && chown -R sandbox:sandbox /workspace /tmp/npm-cache

WORKDIR /workspace

USER sandbox
