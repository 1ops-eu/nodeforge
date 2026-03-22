# Stack Example

Demonstrates `kind: stack` — grouping related resources into a single deployable application boundary.

## What it does

Defines a "blog-stack" with two resources:

1. **nginx-config** (`file_template`) — renders an Nginx reverse-proxy config
2. **blog-app** (`compose_project`) — deploys the application via Docker Compose, depending on the Nginx config being in place first

Resources are executed in dependency order: `nginx-config` first, then `blog-app`.

## Key concepts

- **`resources`** — inline list of resource blocks, each with a `name`, `kind`, and `config`
- **`depends_on`** — declares ordering between resources (validated for missing refs and cycles)
- **Topological sorting** — the planner automatically resolves the correct execution order
- **Step prefixing** — plan steps are prefixed with the resource name for traceability (e.g. `blog-app/pull_images`)

## Usage

```bash
nodeforge validate examples/stack/stack.yaml
nodeforge plan examples/stack/stack.yaml
nodeforge apply examples/stack/stack.yaml
```

## Structure

```
stack/
  stack.yaml      # The stack spec
  README.md       # This file
```
