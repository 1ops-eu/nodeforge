# loft-cli — multi-stage Docker image (wheel-based)
#
# Build:
#   docker build -t loft-cli:latest .
#
# Run:
#   docker run --rm loft-cli:latest --help
#   docker run --rm -v ~/.ssh:/root/.ssh:ro \
#              -v $(pwd)/my-server.yaml:/spec.yaml:ro \
#              loft-cli:latest apply /spec.yaml

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy each package's source (core must be built first as client depends on it)
COPY packages/core/ packages/core/
COPY packages/client/ packages/client/

RUN python -m pip install --upgrade pip build \
    && python -m build --wheel packages/core \
    && python -m build --wheel packages/client

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Install core first, then client (which depends on core)
COPY --from=builder /build/packages/core/dist/*.whl /tmp/core/
COPY --from=builder /build/packages/client/dist/*.whl /tmp/client/

RUN python -m pip install --no-cache-dir /tmp/core/*.whl /tmp/client/*.whl \
    && rm -rf /tmp/core /tmp/client

# Non-root user for safer container execution
RUN useradd --create-home --shell /bin/bash loft-cli
USER loft-cli

ENTRYPOINT ["loft-cli"]
CMD ["--help"]
