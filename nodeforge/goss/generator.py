"""Generate a goss YAML spec from a BootstrapSpec.

The generated spec is driven entirely by the live spec values — admin user name,
SSH port, firewall settings, WireGuard interface, etc. — so it always matches
exactly what nodeforge configured on the server.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from nodeforge.specs.bootstrap_schema import BootstrapSpec


def generate_goss_yaml(spec: "BootstrapSpec") -> str:
    """Return a goss-compatible YAML string for the given BootstrapSpec.

    The spec drives every check: no hardcoded user names, ports, or interfaces.
    """
    doc: dict = {}

    # ------------------------------------------------------------------ #
    # user: admin account must exist in the sudo group
    # ------------------------------------------------------------------ #
    username = spec.admin_user.name
    doc["user"] = {
        username: {
            "exists": True,
            "groups": list(spec.admin_user.groups),
            "home": f"/home/{username}",
            "shell": "/bin/bash",
        }
    }

    # ------------------------------------------------------------------ #
    # file: sshd_config checks — cumulative based on what is configured
    # ------------------------------------------------------------------ #
    sshd_contains: list[str] = []

    if spec.ssh.port != 22:
        sshd_contains.append(f"/^Port\\s+{spec.ssh.port}/")

    if spec.ssh.disable_root_login:
        sshd_contains.append("/^PermitRootLogin\\s+no/")

    if spec.ssh.disable_password_auth and spec.admin_user.pubkeys:
        sshd_contains.append("/^PasswordAuthentication\\s+no/")
        sshd_contains.append("/^PubkeyAuthentication\\s+yes/")

    sshd_entry: dict = {"exists": True}
    if sshd_contains:
        sshd_entry["contains"] = sshd_contains

    doc["file"] = {"/etc/ssh/sshd_config": sshd_entry}

    # authorized_keys must exist and be non-empty when pubkeys were deployed
    if spec.admin_user.pubkeys:
        doc["file"][f"/home/{username}/.ssh/authorized_keys"] = {
            "exists": True,
            "mode": "0600",
            "contains": ["/^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256)\\s+/"],
        }
        doc["file"][f"/home/{username}/.ssh"] = {
            "exists": True,
            "mode": "0700",
            "filetype": "directory",
        }

    # WireGuard config file must exist, be restricted, and contain expected address
    if spec.wireguard.enabled:
        iface = spec.wireguard.interface
        wg_addr = spec.wireguard.address.split("/")[0]  # strip CIDR for content match
        doc["file"][f"/etc/wireguard/{iface}.conf"] = {
            "exists": True,
            "mode": "0600",
            "contains": [
                "/\\[Interface\\]/",
                f"/Address\\s*=\\s*{wg_addr}/",
            ],
        }

    # ------------------------------------------------------------------ #
    # service: ssh must be enabled and running; ufw and wg-quick if active
    # ------------------------------------------------------------------ #
    doc["service"] = {
        "ssh": {"enabled": True, "running": True},
    }

    if spec.firewall.provider == "ufw":
        doc["service"]["ufw"] = {"enabled": True, "running": True}

    if spec.wireguard.enabled:
        iface = spec.wireguard.interface
        doc["service"][f"wg-quick@{iface}"] = {"enabled": True, "running": True}

    # ------------------------------------------------------------------ #
    # port: SSH port must be listening; port 22 must NOT be if port changed
    # ------------------------------------------------------------------ #
    doc["port"] = {
        f"tcp:{spec.ssh.port}": {
            "listening": True,
            "ip": ["0.0.0.0"],
        }
    }

    if spec.ssh.port != 22:
        doc["port"]["tcp:22"] = {"listening": False}

    if spec.wireguard.enabled:
        doc["port"]["udp:51820"] = {"listening": True}

    # ------------------------------------------------------------------ #
    # package: wireguard-tools must be installed when WireGuard is enabled
    # ------------------------------------------------------------------ #
    if spec.wireguard.enabled:
        doc["package"] = {
            "wireguard-tools": {"installed": True},
        }

    # ------------------------------------------------------------------ #
    # command: UFW status and WireGuard interface checks
    # ------------------------------------------------------------------ #
    commands: dict = {}

    if spec.firewall.provider == "ufw":
        ufw_stdout = [
            "/Status:\\s+active/",
            "/Default:\\s+deny\\s+\\(incoming\\)/",
            f"/{spec.ssh.port}\\/tcp\\s+ALLOW\\s+IN/",
        ]
        if spec.wireguard.enabled:
            ufw_stdout.append("/51820\\/udp\\s+ALLOW\\s+IN/")
        commands["ufw status verbose"] = {
            "exit-status": 0,
            "stdout": ufw_stdout,
            "timeout": 10000,
        }

    if spec.wireguard.enabled:
        iface = spec.wireguard.interface
        wg_addr = spec.wireguard.address.split("/")[0]
        commands[f"ip address show {iface}"] = {
            "exit-status": 0,
            "stdout": [f"/{iface}/", f"/{wg_addr}/"],
            "timeout": 5000,
        }
        commands[f"wg show {iface}"] = {
            "exit-status": 0,
            "stdout": [f"/interface: {iface}/"],
            "timeout": 5000,
        }

    if commands:
        doc["command"] = commands

    # ------------------------------------------------------------------ #
    # Serialise — use a header comment so the file is self-documenting
    # ------------------------------------------------------------------ #
    header = (
        f"# nodeforge goss spec — auto-generated for '{spec.meta.name}'\n"
        f"# Target: {spec.host.address}  Admin: {spec.admin_user.name}  SSH port: {spec.ssh.port}\n"
        f"# Run on the server:  goss -g ~/.goss/goss.yaml validate\n"
        f"#\n"
    )
    return header + yaml.dump(doc, default_flow_style=False, sort_keys=True, allow_unicode=True)
