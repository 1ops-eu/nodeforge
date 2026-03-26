# Backup Job Example

Define a scheduled PostgreSQL backup with retention.

## What it does

1. Connects to the target server via SSH
2. Creates the backup destination directory
3. Writes a backup shell script to `/usr/local/bin/loft-cli-backup-app-db.sh`
4. Creates a systemd oneshot service to run the script
5. Creates a systemd timer to trigger the backup on schedule
6. Enables and starts the timer

## Usage

```bash
loft-cli validate examples/backup-job/backup-job.yaml
loft-cli plan examples/backup-job/backup-job.yaml
loft-cli apply examples/backup-job/backup-job.yaml
```

## Backup Types

- `postgres_dump` -- runs `pg_dump` and compresses with gzip
- `directory` -- creates a tar.gz archive of a directory

## Notes

- The backup script, service file, and timer file are all visible in the plan
- Retention is enforced by the script itself (keeps N most recent, deletes older)
- For containerized PostgreSQL, set `docker_exec` to the container name
- The schedule uses systemd's OnCalendar syntax
