# nodeforge/local/ — Local Filesystem Operations

This package manages all local state that nodeforge persists after a successful apply: SSH config fragments, WireGuard key material, the SQLite inventory database, and SSH key generation.

---

## Files

| File | Purpose |
|---|---|
| `ssh_config.py` | SSH conf.d fragment management: write, remove, backup, ensure Include directive |
| `wireguard_store.py` | WireGuard state persistence: server/client keys, configs, metadata |
| `inventory_db.py` | SQLite inventory database with versionize historization (SCD Type 2 pattern) |
| `inventory.py` | High-level inventory recording functions called post-apply (`record_bootstrap()`, `record_service_apply()`) |
| `keys.py` | SSH key pair generation: auto-generates missing ed25519 keys before apply |
| `ddl/` | SQL DDL definitions for the inventory schema |
| `ddl/bootstrap_tables.py` | Domain table DDL: `tv_server`, `tv_server_service`, `tv_run` |
| `ddl/versionize_system.py` | Versionize system DDL: temporal history generation triggers |
| `__init__.py` | Empty package marker |

---

## SSH Config (`ssh_config.py`)

Manages per-host SSH config fragments under `{ssh_conf_d_base}/{host_name}.conf` (default: `~/.ssh/conf.d/nodeforge/`).

- `write_ssh_conf_d(host_name, address, user, port, identity_file)` — writes a Host entry with IdentityFile and IdentitiesOnly
- `remove_ssh_conf_d(host_name)` — deletes the fragment
- `ensure_include(config_path)` — ensures `Include {ssh_conf_d_base}/*` exists in `~/.ssh/config` (single glob covers all fragments)
- `backup_ssh_config(config_path)` — creates a timestamped `.bak` copy

The base directory is addon-overridable via `register_local_paths()`.

---

## WireGuard Store (`wireguard_store.py`)

Persists WireGuard state under `{wg_state_base}/{host_name}/` (default: `~/.wg/nodeforge/{host}/`):

```
{host_name}/
  private.key     server Curve25519 private key (mode 0600)
  public.key      server public key (mode 0644)
  wg0.conf        server wg-quick config as deployed (mode 0600)
  client.key      auto-generated client private key (mode 0600, write-once)
  client.conf     client wg-quick config for local use (mode 0600)
  metadata.json   interface details, peer config, deployment provenance (mode 0644)
```

`client.key` is **write-once**: it is only created on first run and reused on subsequent runs for stable peer identity.

The base directory is addon-overridable via `register_local_paths()`.

---

## Inventory Database (`inventory_db.py`)

SQLite-based local inventory with a versionize historization pattern (similar to SCD Type 2):

- Every `INSERT` into a `vv_*` view is intercepted by generated triggers that maintain temporal history in `tv_*` tables.
- Full audit trail: every change to a server record is preserved with timestamps and `version_changed_by`.
- Three domain entities: **servers**, **server services**, and **runs**.

### Key methods

- `upsert_server(...)` — insert/update server record via `vv_server` view
- `get_server(id)` / `list_servers()` — query current server state
- `upsert_service(...)` — insert/update service record via `vv_server_service` view
- `record_run(...)` — record apply execution metadata via `vv_run` view
- `get_run(id)` / `list_runs(server_id)` — query run history

### Schema notes

- Uses Python's built-in `sqlite3` — no native dependencies.
- The commercial edition can swap in SQLCipher by changing the import.
- The versionize system (`ddl/versionize_system.py`) generates `CREATE VIEW`, `CREATE TRIGGER` DDL dynamically for any table matching the `tv_*` naming convention.

---

## SSH Key Generation (`keys.py`)

`ensure_admin_keys(spec, console)` — generates missing ed25519 SSH key pairs before apply:

- Iterates `admin_user.pubkeys` looking for `.pub` files whose private key counterpart is missing.
- Calls `ssh-keygen -t ed25519` to generate the pair.
- Only runs when the kind's `KindHooks.needs_key_generation` flag is `True`.

---

## Inventory Recording (`inventory.py`)

High-level functions called post-apply by the CLI via `KindHooks.on_inventory_record`:

- `record_bootstrap(db, spec, result)` — upserts server record with bootstrap status, SSH config, WireGuard state
- `record_service_apply(db, spec, result)` — upserts service metadata for the target server

---

## Design Decisions

- **Single glob Include**: `~/.ssh/config` gets one `Include {base}/*` line covering all fragments — no per-file Include management.
- **Write-once client keys**: WireGuard client private keys are never overwritten, ensuring stable peer identity across re-runs.
- **Versionize pattern**: the temporal history system is generic and works for any `tv_*` table, making it easy to add new domain entities.
- **All paths addon-overridable**: SSH conf.d, WireGuard state, inventory DB, and log directory paths are all resolved via `get_local_paths()`.
