# File Template Example

Renders a Jinja2 template with variables and uploads the result to a remote server.

## What it does

1. Connects to the target server via SSH
2. Creates the parent directory for the destination file
3. Renders `templates/nginx-site.conf.j2` with the provided variables
4. Uploads the rendered content to `/etc/nginx/sites-available/app.example.com`
5. Sets file permissions (0644) and ownership (root:root)

## Usage

```bash
nodeforge validate examples/file-template/file-template.yaml
nodeforge plan examples/file-template/file-template.yaml
nodeforge apply examples/file-template/file-template.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- nginx installed on the server (use a `kind: service` spec first)

## Notes

- Templates are rendered at **plan time** -- the fully rendered content appears in the execution plan, making it fully reviewable before apply
- Variables are simple key-value string pairs passed to the Jinja2 template context
- Template source paths are resolved relative to the spec file location
- `StrictUndefined` is used -- any undefined variable in the template will cause a clear error at plan time
