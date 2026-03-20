# Compose Project Example

Deploys a multi-service Docker Compose stack with template rendering and health checks.

## What it does

1. Connects to the target server via SSH
2. Creates the project directory `/opt/demo-stack`
3. Creates managed subdirectory `data/`
4. Renders `templates/nginx.conf.j2` with variables and uploads to the project directory
5. Uploads `docker-compose.yml` to the project directory
6. Validates the compose configuration (`docker compose config`)
7. Pulls container images (`docker compose pull`)
8. Starts the stack (`docker compose up -d`)
9. Waits for all containers to be healthy (polls for up to 120 seconds)

## Usage

```bash
nodeforge validate examples/compose-project/compose-project.yaml
nodeforge plan examples/compose-project/compose-project.yaml
nodeforge apply examples/compose-project/compose-project.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- Docker and Docker Compose v2 installed (use a `kind: service` spec with `docker.enabled: true` first)

## Notes

- The compose file is uploaded as-is (not rendered through Jinja2) -- only files listed in `templates` are rendered
- Template dest paths are relative to the project directory unless they start with `/`
- Health checks poll `docker compose ps --format json` and check container state and health status
- `pull_before_up: true` (default) ensures the latest images are pulled before starting
