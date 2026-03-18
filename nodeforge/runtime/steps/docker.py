"""Docker installation commands."""

from __future__ import annotations


def install_docker() -> str:
    return "bash -c 'curl -fsSL https://get.docker.com | sh'"


def enable_docker() -> str:
    return "systemctl enable --now docker"


def docker_version_check() -> str:
    return "docker --version"
