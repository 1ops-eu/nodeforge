# HTTP Check Example

GET-only HTTP readiness probe with retry and backoff.

## What it does

1. Connects to the target server via SSH
2. Performs a GET request to the specified URL
3. Retries up to the configured number of attempts if the expected status is not returned
4. Reports success or failure after all attempts

## Usage

```bash
loft-cli validate examples/http-check/http-check.yaml
loft-cli plan examples/http-check/http-check.yaml
loft-cli apply examples/http-check/http-check.yaml
```

## Stack Integration

`http_check` is designed to be used as a dependency gate in stacks:

```yaml
kind: stack
resources:
  - name: app
    kind: compose_project
    spec: { ... }
  - name: app-ready
    kind: http_check
    spec:
      check:
        url: http://localhost:8080/health
    depends_on: [app]
  - name: configure-app
    kind: file_template
    spec: { ... }
    depends_on: [app-ready]
```

## Notes

- Only GET requests are supported -- no request bodies, no mutations
- No response templating or chaining -- this is a readiness gate, not an API client
- The check runs on the target server (agent-side), so `localhost` URLs work
