# Systemd Unit Example

Deploy a host-native application as a systemd service with optional log rotation.

## What it does

1. Connects to the target server via SSH
2. Writes a systemd unit file to `/etc/systemd/system/myapp.service`
3. Runs `systemctl daemon-reload`
4. Enables and restarts the service
5. Verifies the service is active
6. Optionally writes a logrotate configuration

## Usage

```bash
nodeforge validate examples/systemd-unit/systemd-unit.yaml
nodeforge plan examples/systemd-unit/systemd-unit.yaml
nodeforge apply examples/systemd-unit/systemd-unit.yaml
```

## Prerequisites

- A bootstrapped server with SSH access on port 2222
- The application binary installed at the path specified in `exec_start`

## Notes

- The unit file is fully rendered at plan time and visible in the execution plan
- Re-running is idempotent -- unchanged unit files are not rewritten
- The `restart` field maps directly to systemd's `Restart=` directive
- Log rotation uses logrotate and is optional (disabled by default)
