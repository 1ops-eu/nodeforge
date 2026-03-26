"""Domain table DDLs for loft-cli inventory.

Tables use the versionize pattern (tv_* with version columns, vv_* views auto-generated).
Column structure adapted from RFC section 17 + vm_wizard versionize pattern.
"""

TV_SERVER = """
CREATE TABLE IF NOT EXISTS tv_server (
    id                  TEXT NOT NULL,
    name                TEXT NOT NULL,
    address             TEXT NOT NULL,
    os_family           TEXT,
    bootstrap_status    TEXT NOT NULL,
    ssh_alias           TEXT,
    ssh_host            TEXT,
    ssh_user            TEXT,
    ssh_port            INTEGER,
    ssh_identity_file   TEXT,
    wireguard_enabled   INTEGER NOT NULL DEFAULT 0,
    wireguard_interface TEXT,
    wireguard_address   TEXT,
    version_valid_from  TEXT NOT NULL,
    version_valid_to    TEXT NOT NULL,
    version_changed_by  TEXT NOT NULL,
    version_changed_at  TEXT NOT NULL,
    version_is_deleted  TEXT NOT NULL,
    CONSTRAINT pk_tv_server
        PRIMARY KEY (id, version_valid_from)
);
"""

TV_SERVER_SERVICE = """
CREATE TABLE IF NOT EXISTS tv_server_service (
    server_id           TEXT NOT NULL,
    service_type        TEXT NOT NULL,
    service_name        TEXT NOT NULL,
    status              TEXT NOT NULL,
    metadata_json       TEXT,
    version_valid_from  TEXT NOT NULL,
    version_valid_to    TEXT NOT NULL,
    version_changed_by  TEXT NOT NULL,
    version_changed_at  TEXT NOT NULL,
    version_is_deleted  TEXT NOT NULL,
    CONSTRAINT pk_tv_server_service
        PRIMARY KEY (server_id, service_type, service_name, version_valid_from)
);
"""

TV_RUN = """
CREATE TABLE IF NOT EXISTS tv_run (
    id                  TEXT NOT NULL,
    server_id           TEXT,
    spec_hash           TEXT NOT NULL,
    plan_hash           TEXT NOT NULL,
    kind                TEXT NOT NULL,
    status              TEXT NOT NULL,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    metadata_json       TEXT,
    version_valid_from  TEXT NOT NULL,
    version_valid_to    TEXT NOT NULL,
    version_changed_by  TEXT NOT NULL,
    version_changed_at  TEXT NOT NULL,
    version_is_deleted  TEXT NOT NULL,
    CONSTRAINT pk_tv_run
        PRIMARY KEY (id, version_valid_from)
);
"""

# Tables to create and versionize, in order
DOMAIN_TABLES = [
    ("tv_server", TV_SERVER),
    ("tv_server_service", TV_SERVER_SERVICE),
    ("tv_run", TV_RUN),
]
