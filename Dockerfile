# nodeforge — multi-stage Docker image (wheel-based)
#
# Build:
#   docker build -t nodeforge:latest .
#
# Run:
#   docker run --rm nodeforge:latest --help
#   docker run --rm -v ~/.ssh:/root/.ssh:ro \
#              -e NODEFORGE_SQLCIPHER_KEY=your-key \
#              -v $(pwd)/my-server.yaml:/spec.yaml:ro \
#              nodeforge:latest apply /spec.yaml

# ── Stage 1: builder ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# sqlcipher3 requires the SQLCipher dev library at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlcipher-dev \
        gcc \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

COPY pyproject.toml README.md LICENSE ./
COPY nodeforge ./nodeforge

RUN python -m pip install --upgrade pip build \
    && python -m build --wheel

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim

# sqlcipher3 requires the SQLCipher shared library at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        libsqlcipher0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /build/dist/*.whl /tmp/

RUN python -m pip install --no-cache-dir /tmp/*.whl \
    && rm -rf /tmp/*.whl

# Non-root user for safer container execution
RUN useradd --create-home --shell /bin/bash nodeforge
USER nodeforge

ENTRYPOINT ["nodeforge"]
CMD ["--help"]
