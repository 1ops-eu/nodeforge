# Systemd Timer Example

Deploy a scheduled task via systemd timer and companion oneshot service.

## What it does

1. Connects to the target server via SSH
2. Writes a companion `.service` file (Type=oneshot) to run the command
3. Writes a `.timer` file with the configured calendar schedule
4. Runs `systemctl daemon-reload`
5. Enables and starts the timer with `systemctl enable --now`
6. Verifies the timer is active

## Usage

```bash
loft-cli validate examples/systemd-timer/systemd-timer.yaml
loft-cli plan examples/systemd-timer/systemd-timer.yaml
loft-cli apply examples/systemd-timer/systemd-timer.yaml
```

## Notes

- The `on_calendar` field uses systemd's calendar event syntax (e.g. `*-*-* 02:00:00` for daily at 2am)
- `persistent: true` means missed runs (e.g. during downtime) are executed on boot
- Both the `.timer` and `.service` files are fully visible in the plan
