# Multi-Container Example

Deploys multiple Docker containers including an API server, a background worker, and Redis.

## What it does

1. Installs Docker
2. Deploys three containers:
   - `api` — application API server on port 3000 with HTTP health check
   - `worker` — background job processor (no exposed ports)
   - `redis` — Redis 7 on port 6379
3. Each container uses `env_file` for secret injection

## Usage

```bash
loft-cli validate examples/multi-container/multi-container.yaml
loft-cli plan examples/multi-container/multi-container.yaml
loft-cli apply examples/multi-container/multi-container.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- `.env.api` and `.env.worker` files in the spec directory with secrets

## Notes

- The `env_file` field references a file on the remote host that Docker will read at container startup
- Each container has its own health check via the `checks` block
