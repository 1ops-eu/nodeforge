# nodeforge/specs/ — Spec Schemas, Loader, and Validators

This package defines the YAML spec schemas (Pydantic v2 models), the YAML loader with environment variable resolution, and cross-field validators.

---

## Files

| File | Purpose |
|---|---|
| `loader.py` | YAML loading, `${VAR}` environment variable resolution, `.env` file support, registry-based model dispatch |
| `bootstrap_schema.py` | Pydantic v2 models for `kind: bootstrap` specs |
| `service_schema.py` | Pydantic v2 models for `kind: service` specs |
| `validators.py` | Cross-field validation beyond Pydantic schema checks (SSH port ranges, WireGuard completeness, etc.) |
| `__init__.py` | Empty package marker |

---

## Loader (`loader.py`)

Entry point: `load_spec(path, *, strict_env=True, env_file=None) -> AnySpec`

### Environment variable resolution

The `${VAR}` pattern is resolved recursively across all string values in the parsed YAML:

- **Strict mode** (default): raises `SpecLoadError` with the exact field path if a variable is not set (e.g., `"Unresolved variable '${DB_PASSWORD}' in field 'postgres.create_role.password_env'"`)
- **Passthrough mode** (`strict_env=False`): leaves `${VAR}` unchanged in the output

### `.env` file support

`load_env_file(path) -> dict[str, str]` parses `.env` files supporting:
- `KEY=VALUE`, `KEY="VALUE"`, `KEY='VALUE'`
- `export KEY=VALUE` (prefix stripped)
- Comments (`#`) and blank lines

Variables are loaded into `os.environ` via `setdefault()` — existing environment variables always take precedence.

### Model dispatch

After YAML parsing and env var resolution, the `kind` field is looked up in `SPEC_REGISTRY` to find the matching Pydantic model class. Unknown kinds produce a clear error listing all registered kinds.

---

## Bootstrap Schema (`bootstrap_schema.py`)

`BootstrapSpec` — the top-level model for `kind: bootstrap`. Contains these blocks:

| Block | Model | Purpose |
|---|---|---|
| `meta` | `MetaBlock` | Spec name and description |
| `host` | `HostBlock` | Target hostname, address, OS family |
| `login` | `LoginBlock` | Root login credentials (user, key, password, port) |
| `admin_user` | `AdminUserBlock` | Admin user name, groups, pubkey paths |
| `ssh` | `SSHBlock` | Post-bootstrap SSH port, root/password disable flags |
| `firewall` | `FirewallBlock` | UFW provider, ssh_only, registered_peers_only |
| `wireguard` | `WireGuardBlock` | WG interface, address, key file, endpoint, peer |
| `local` | `LocalBlock` | state_dir, ssh_config settings, inventory settings |
| `checks` | `list[CheckBlock]` | Postflight verification checks |

---

## Service Schema (`service_schema.py`)

`ServiceSpec` — the top-level model for `kind: service`. Contains:

| Block | Model | Purpose |
|---|---|---|
| `meta` | `MetaBlock` | Spec name and description |
| `host` | `HostBlock` | Target hostname and address |
| `login` | `ServiceLoginBlock` | Admin login (defaults to port 2222) |
| `postgres` | `PostgresBlock` | PostgreSQL version, listen addresses, role/db creation |
| `docker` | `DockerBlock` | Docker enabled flag |
| `containers` | `list[ContainerBlock]` | Container definitions with image, ports, env, healthcheck |
| `local` | `ServiceLocalBlock` | state_dir, inventory settings |
| `checks` | `list[CheckBlock]` | Postflight verification checks |

---

## Validators (`validators.py`)

Entry point: `validate_spec(spec) -> list[ValidationIssue]`

Performs semantic validation beyond what Pydantic schema checks can enforce:

### Bootstrap validations
- SSH port in valid range (1-65535)
- `disable_password_auth=true` requires at least one pubkey
- WireGuard completeness (all required fields when `enabled=true`)
- `registered_peers_only` warns when WireGuard is disabled
- SSH port same as login port warning
- OS family support check

### Service validations
- Postgres role without `password_env` warning
- Container without image error
- Containers defined but Docker not enabled warning

Each issue is a `ValidationIssue` with severity (`error` or `warning`), field path, and message.

---

## Design Decisions

- **Pydantic v2**: all schemas use `BaseModel` with `model_validate()` for strict type checking and clear error messages.
- **Field paths in errors**: env var resolution tracks the YAML path (e.g., `postgres.create_role.password_env`) for actionable error messages.
- **Shared blocks**: `MetaBlock`, `HostBlock`, `CheckBlock`, `InventoryBlock` are defined once in `bootstrap_schema.py` and reused by `service_schema.py`.
