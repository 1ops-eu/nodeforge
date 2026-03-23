# Compose Project Example

Deploys a multi-service Docker Compose stack with template rendering and health checks.

## What it does

1. Connects to the target server via SSH
2. Installs Docker (if not already present)
3. Creates the project directory `/opt/demo-stack`
4. Creates managed subdirectory `data/`
5. Renders `templates/app.conf.j2` with variables and uploads to the project directory
6. Uploads `docker-compose.yml` to the project directory
7. Validates the compose configuration (`docker compose config`)
8. Pulls container images (`docker compose pull`)
9. Starts the stack (`docker compose up -d`)
10. Waits for all containers to be healthy (polls for up to 120 seconds)

## Usage

```bash
nodeforge validate examples/compose-project/compose-project.yaml
nodeforge plan examples/compose-project/compose-project.yaml
nodeforge apply examples/compose-project/compose-project.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222

## Notes

- The compose file is uploaded as-is (not rendered through Jinja2) -- only files listed in `templates` are rendered
- Template dest paths are relative to the project directory unless they start with `/`
- Health checks poll `docker compose ps --format json` and check container state and health status
- `pull_before_up: true` (default) ensures the latest images are pulled before starting
