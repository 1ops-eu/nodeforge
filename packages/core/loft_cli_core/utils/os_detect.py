from dataclasses import dataclass

SUPPORTED_OS_FAMILIES = {"debian", "ubuntu"}


@dataclass
class OSInfo:
    distro: str
    codename: str
    version: str
    family: str  # "debian" for both Debian and Ubuntu


def detect_os(session) -> "OSInfo":
    """Detect remote OS via /etc/os-release. Asserts Debian/Ubuntu in V1."""
    result = session.run("cat /etc/os-release", hide=True)
    info = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            info[k.strip()] = v.strip().strip('"')

    distro = info.get("ID", "unknown").lower()
    codename = info.get("VERSION_CODENAME", info.get("UBUNTU_CODENAME", "unknown"))
    version = info.get("VERSION_ID", "unknown")

    # Determine family
    if distro in ("ubuntu",) or distro in ("debian",):
        family = "debian"
    else:
        family = distro

    if family not in SUPPORTED_OS_FAMILIES:
        raise RuntimeError(f"Unsupported OS '{distro}'. loft-cli V1 supports Debian/Ubuntu only.")

    return OSInfo(distro=distro, codename=codename, version=version, family=family)
