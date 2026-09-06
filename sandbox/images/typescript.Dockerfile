# Base TypeScript sandbox image for Penthos.
#
# Built on the Node.js image with TypeScript tooling added. ARM64-compatible,
# minimal, non-root. No network access is provided at execution time.
#
# Build:
#   docker build -f sandbox/images/typescript.Dockerfile -t penthos-sandbox:typescript sandbox

FROM node:20-bookworm-slim

ENV NPM_CONFIG_CACHE=/tmp/npm-cache \
    NODE_ENV=production

# The official Node image ships a 'node' user at UID 1000, so the sandbox
# user uses UID 1001 here to avoid a collision.
# Global tooling is installed under /usr/local (npm's default global prefix)
# so it survives the /workspace bind mount at execution time, which shadows
# whatever the image placed in /workspace.
RUN useradd --create-home --shell /bin/sh --uid 1001 sandbox \
    && mkdir -p /workspace /tmp/npm-cache \
    && chown -R sandbox:sandbox /workspace /tmp/npm-cache

# Install TypeScript tooling in the global image (build-time only).
RUN npm install --global typescript@5.6.3 tsx@4.19.2

WORKDIR /workspace

USER sandbox
