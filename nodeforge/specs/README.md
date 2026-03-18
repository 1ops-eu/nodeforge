# nodeforge/specs/ — Spec Schemas, Loader, and Validators

This package defines the YAML spec schemas (Pydantic v2 models), the YAML loader with environment variable resolution, and cross-field validators.

---

## Files

| File | Purpose |
|---|---|
| `loader.py` | YAML loading, `${[prefix:]key[:-default]}` value resolution via resolver registry, `.env` file support, registry-based model dispatch |
| `bootstrap_schema.py` | Pydantic v2 models for `kind: bootstrap` specs |
| `service_schema.py` | Pydantic v2 models for `kind: service` specs |
| `validators.py` | Cross-field validation beyond Pydantic schema checks (SSH port ranges, WireGuard completeness, etc.) |
| `__init__.py` | Empty package marker |

---

## Loader (`loader.py`)

Entry point: `load_spec(path, *, strict_env=True, env_file=None) -> AnySpec`

### Value resolution

All `${...}` tokens in string values are resolved recursively across the entire parsed YAML structure via the **resolver registry** (`nodeforge/registry/resolvers.py`).

#### Token syntax

| Token | Meaning |
|---|---|
| `${VAR}` | Bare reference — permanent shorthand for `${env:VAR}`. Never deprecated. |
| `${env:VAR}` | Explicit environment variable lookup. |
| `${file:/path/to/file}` | Read file contents (trailing newline stripped). `~` is expanded. |
| `${prefix:key}` | Dispatch to any addon-registered resolver (e.g. `sops`, `vault`). |
| `${VAR:-default}` | Use *default* if the resolved value is `None`. Works with any prefix: `${env:VAR:-fallback}`, `${file:/opt/key.pub:-}`, etc. |

#### Resolution modes

- **Strict mode** (default): raises `SpecLoadError` with the exact field path if a token resolves to `None` and has no default (e.g., `"Unresolved variable '${DB_PASSWORD}' in field 'postgres.create_role.password_env'"`)
- **Passthrough mode** (`strict_env=False`): leaves unresolved `${...}` tokens unchanged in the output

#### Unknown prefix

If a prefix is not registered, `_resolve_values` raises `SpecLoadError` naming the unknown prefix, all registered prefixes, and a hint to check for a missing addon.

#### Extending resolution via addons

External addons register additional resolvers by calling `register_resolver(prefix, fn)` in their `register()` function. The resolver callable has the signature `(key: str) -> str | None`.

```python
from nodeforge.registry import register_resolver

def register():
    register_resolver("sops", _resolve_sops)

def _resolve_sops(key: str) -> str | None:
    # key format: "path/to/secrets.yaml#json.dot.path"
    ...
```

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
| `nginx` | `NginxBlock` | Nginx reverse proxy: enabled flag, site definitions |
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
- Nginx enabled with no sites warning
- Nginx site without domain error
- Nginx SSL without certificate paths error
- Nginx site listen port range check

Each issue is a `ValidationIssue` with severity (`error` or `warning`), field path, and message.

---

## Design Decisions

- **Pydantic v2**: all schemas use `BaseModel` with `model_validate()` for strict type checking and clear error messages.
- **Field paths in errors**: env var resolution tracks the YAML path (e.g., `postgres.create_role.password_env`) for actionable error messages.
- **Shared blocks**: `MetaBlock`, `HostBlock`, `CheckBlock`, `InventoryBlock` are defined once in `bootstrap_schema.py` and reused by `service_schema.py`.
