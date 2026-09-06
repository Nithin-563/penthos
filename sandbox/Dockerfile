# Penthos sandbox base image (meta).
#
# This file exists so the sandbox/ directory has a canonical "Dockerfile"
# entrypoint for tooling that looks for one. The three language-specific
# images in sandbox/images/ are the real artifacts used by the runner.
#
# Building this file alone only produces an empty marker image and is not
# used for execution. See sandbox/images/*.Dockerfile for the real images,
# or use the build helper in sandbox/runner.py.

FROM scratch

COPY images/python.Dockerfile /python.Dockerfile
COPY images/node.Dockerfile /node.Dockerfile
COPY images/typescript.Dockerfile /typescript.Dockerfile
