"""Docker container management commands."""

from __future__ import annotations

from nodeforge.specs.service_schema import ContainerBlock


def pull_image(image: str) -> str:
    return f"docker pull {image}"


def stop_container(name: str) -> str:
    return f"bash -c 'docker stop {name} 2>/dev/null || true'"


def remove_container(name: str) -> str:
    return f"bash -c 'docker rm {name} 2>/dev/null || true'"


def run_container(container: ContainerBlock) -> str:
    """Build docker run command from ContainerBlock."""
    parts = ["docker run -d"]
    parts.append(f"--name {container.name}")
    parts.append(f"--restart {container.restart}")

    for port_mapping in container.ports:
        parts.append(f"-p {port_mapping}")

    for k, v in container.env.items():
        parts.append(f"-e {k}={v!r}")

    if container.env_file:
        parts.append(f"--env-file {container.env_file}")

    parts.append(container.image)
    return " \\\n  ".join(parts)


def container_running_check(name: str) -> str:
    return f"docker inspect --format='{{{{.State.Running}}}}' {name}"
