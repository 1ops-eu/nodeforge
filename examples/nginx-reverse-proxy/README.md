# Nginx Reverse Proxy Example

Installs nginx and configures it as a reverse proxy for a single backend application.

## What it does

1. Installs nginx via apt
2. Enables the nginx systemd service
3. Removes the default nginx site
4. Writes a reverse proxy config for `app.example.com` proxying to `127.0.0.1:8080`
5. Validates config and reloads nginx

## Usage

```bash
nodeforge validate examples/nginx-reverse-proxy/nginx-reverse-proxy.yaml
nodeforge plan examples/nginx-reverse-proxy/nginx-reverse-proxy.yaml
nodeforge apply examples/nginx-reverse-proxy/nginx-reverse-proxy.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- A backend application listening on port 8080

## Notes

- The `upstream` field defaults to `127.0.0.1` when omitted
- For SSL termination, set `ssl: true` and provide `ssl_certificate` and `ssl_certificate_key` paths
