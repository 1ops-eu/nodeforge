# nodeforge/runtime/ — SSH Sessions and Plan Execution

This package contains the SSH transport layer and the plan execution engine. It is the "apply" phase of the pipeline — where plans become actions.

---

## Files

| File | Purpose |
|---|---|
| `executor.py` | Plan execution engine: walks the step list, dispatches to registered handlers, enforces gates and dependencies, tracks results |
| `ssh.py` | Fabric SSH session wrapper: command execution, file upload, connection testing |
| `steps/` | Shell command builders for each domain (bootstrap, wireguard, postgres, docker, container) |
| `__init__.py` | Empty package marker |

---

## Executor (`executor.py`)

The `Executor` class takes a `Plan`, an `SSHSession`, an `InventoryDB`, and the normalized context/spec, then executes each step in order.

### Core behaviour

1. **Sequential execution**: steps are executed in index order.
2. **Dependency checking**: if any step in `step.depends_on` failed, the dependent step is **skipped**.
3. **Gate enforcement**: if a `gate=True` step fails, the entire plan **aborts** immediately. This is the SSH lockout prevention mechanism.
4. **Preflight abort**: if step 0 (preflight connection check) fails, the plan aborts with a clear "cannot connect" message.
5. **Step dispatch**: each step's `kind` is looked up in `STEP_HANDLER_REGISTRY`. Unknown kinds produce a "required addon installed?" error.
6. **Dry-run mode**: when `dry_run=True`, all steps report success with a `[dry-run]` message.

### Built-in step handlers

| Step Kind | Handler | Description |
|---|---|---|
| `ssh_command` | `_execute_ssh_command()` | Run a shell command on the remote host via SSH |
| `ssh_upload` | `_execute_ssh_upload()` | Upload file content to a remote path (handles `~` expansion) |
| `gate` | `_execute_gate()` | SSH login verification (parses `ssh_check:host:port:user` command format) |
| `verify` | `_execute_verify()` | Non-gate verification: goss validate, postflight checks, SSH commands |
| `local_file_write` | `_execute_local_file_write()` | Write SSH conf.d entry locally |
| `local_command` | `_execute_local_command()` | Backup SSH config, ensure Include, save WireGuard state |
| `local_db_write` | `_execute_local_db_write()` | Initialize/upsert inventory database |

### Result model

- `StepResult` — per-step: index, id, scope, status (success/failed/skipped), output, error, duration
- `ApplyResult` — overall: plan, all step results, final status (success/failed/success_with_local_warnings), timing

---

## SSH Session (`ssh.py`)

The `SSHSession` class wraps a Fabric `Connection` with a clean API:

- `run(cmd, sudo, warn, hide) -> CommandResult` — execute a command remotely
- `upload(local_path, remote_path)` — upload a local file
- `upload_content(content, remote_path, sudo)` — write string content to a remote file via `/tmp` staging
- `test_connection() -> bool` — verify SSH connectivity
- `close()` — close the connection

### Key details

- Uses `_AutoAddConnection` subclass that auto-accepts unknown host keys (required for fresh VMs).
- When password auth is used without a key, explicitly disables key-based auth to prevent Paramiko errors.
- `CommandResult` is a Pydantic model with `ok`, `stdout`, `stderr`, `return_code`.

---

## Step Builders (`steps/`)

Shell command builder modules that generate the exact commands executed on remote hosts:

| File | Domain | Key functions |
|---|---|---|
| `bootstrap.py` | Server hardening | `create_admin_user()`, `install_authorized_keys()`, `write_sshd_config_candidate()`, `disable_root_login()`, `disable_password_auth()`, `finalize_firewall()`, `restrict_ssh_to_wireguard()` |
| `wireguard.py` | WireGuard VPN | `generate_server_config()`, `generate_client_config()`, `enable_wireguard()` |
| `postgres.py` | PostgreSQL | `install_postgres()`, `configure_listen()`, `enable_postgres()`, `create_role()`, `create_database()` |
| `docker.py` | Docker | `install_docker()`, `enable_docker()` |
| `container.py` | Docker containers | `pull_image()`, `stop_container()`, `remove_container()`, `run_container()` |

These modules contain **no execution logic** — they only return shell command strings that the planner embeds in `Step` objects.

---

## Design Decisions

- **Executor is stateful**: it holds references to the SSH session, inventory DB, and context. This allows step handlers to access shared resources without parameter threading.
- **Step handlers are registered, not hardcoded**: the executor looks up handlers in `STEP_HANDLER_REGISTRY`, so addons can add new step kinds.
- **Local failures are warnings, not aborts**: if SSH conf.d or inventory writes fail, the plan continues with `success_with_local_warnings` status — the remote server is still properly configured.
- **Console output via Rich**: step progress is printed with colour-coded icons (green check, red cross, dim circle for skipped).
