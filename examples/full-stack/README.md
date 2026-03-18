# Full Stack Production Example

A realistic production stack combining PostgreSQL, a Docker application container, and nginx as a reverse proxy on a single host.

## What it does

1. **PostgreSQL 16** — installs, configures, creates `appuser` role and `appdb` database
2. **Docker** — installs Docker engine
3. **Application container** — deploys `webapp` on port 8080 with database connection
4. **Nginx reverse proxy** — proxies `app.example.com` to the application on port 8080

## Architecture

```
Internet -> nginx:80 (app.example.com) -> webapp:8080 -> PostgreSQL:5432
```

## Usage

```bash
# Set the database password
export APP_DB_PASSWORD="your-secure-password"

nodeforge validate examples/full-stack/full-stack.yaml
nodeforge plan examples/full-stack/full-stack.yaml
nodeforge apply examples/full-stack/full-stack.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- `APP_DB_PASSWORD` environment variable set

## Notes

- The execution order is: PostgreSQL -> nginx -> Docker -> containers -> inventory
- Each service has its own verification check in the `checks` block
- This demonstrates the core nodeforge value proposition: a single YAML spec defines an entire production-ready stack
