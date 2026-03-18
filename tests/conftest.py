"""Shared pytest fixtures."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _load_nodeforge_addons():
    """Ensure all built-in registries (step handlers, etc.) are loaded for tests."""
    from nodeforge.registry import load_addons

    load_addons()


@pytest.fixture
def bootstrap_yaml_content() -> str:
    return textwrap.dedent("""\
        kind: bootstrap
        meta:
          name: test-node
          description: Test bootstrap spec
        host:
          name: test-node-1
          address: 192.168.1.100
          os_family: debian
        login:
          user: root
          private_key: ~/.ssh/id_ed25519
          port: 22
        admin_user:
          name: admin
          groups:
            - sudo
          pubkeys: []
        ssh:
          port: 2222
          disable_root_login: true
          disable_password_auth: false
        firewall:
          provider: ufw
          ssh_only: true
        wireguard:
          enabled: false
        local:
          ssh_config:
            enabled: true
          inventory:
            enabled: false
        checks: []
    """)


@pytest.fixture
def bootstrap_yaml(tmp_path, bootstrap_yaml_content) -> Path:
    f = tmp_path / "bootstrap.yaml"
    f.write_text(bootstrap_yaml_content)
    return f


@pytest.fixture
def service_yaml(tmp_path) -> Path:
    content = textwrap.dedent("""\
        kind: service
        meta:
          name: test-service
          description: Test service spec
        host:
          name: test-node-1
          address: 192.168.1.100
          os_family: debian
        login:
          user: admin
          private_key: ~/.ssh/id_ed25519
          port: 2222
        postgres:
          enabled: true
          version: "16"
        local:
          inventory:
            enabled: false
        checks: []
    """)
    f = tmp_path / "service.yaml"
    f.write_text(content)
    return f


@pytest.fixture
def mock_ssh_session(mocker):
    """Mocked SSHSession that records commands without executing."""
    session = mocker.MagicMock()
    session.test_connection.return_value = True
    from nodeforge.runtime.ssh import CommandResult

    session.run.return_value = CommandResult(ok=True, stdout="ok", stderr="", return_code=0)
    return session
