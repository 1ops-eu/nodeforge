"""Binary build script for nodeforge-agent (Linux only).

Builds a standalone single-file executable for the server-side agent
using PyInstaller.  The agent binary is intentionally minimal — it only
includes nodeforge-core and nodeforge-agent (no Fabric, no SQLCipher,
no paramiko).

Usage:
    python scripts/build_agent_binary.py

Output:
    dist/nodeforge-agent     (Linux)

The agent binary targets Linux servers only (Debian/Ubuntu).  There is no
macOS or Windows build — the agent runs on managed servers, not developer
machines.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

APP_NAME = "nodeforge-agent"


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd))
    subprocess.check_call(cmd)


def remove_path(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.isfile(path):
        os.remove(path)


def main() -> None:
    # Clean prior build artifacts
    for path in ["build", "dist"]:
        if os.path.exists(path):
            remove_path(path)

    for fname in os.listdir("."):
        if fname.endswith(".spec"):
            remove_path(fname)

    # Ensure build dependencies are present
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "build", "pyinstaller"])

    # Install agent + core packages so PyInstaller can resolve imports.
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "packages/core",
            "packages/agent",
        ]
    )

    # Build single-file executable.
    # --paths ensures both packages are on sys.path for PyInstaller analysis.
    # The agent has no C-extension dependencies (no sqlcipher, no paramiko,
    # no fabric) so no --hidden-import flags are needed for those.
    run(
        [
            "pyinstaller",
            "--onefile",
            "--name",
            APP_NAME,
            "--clean",
            "--paths",
            "packages/core",
            "--paths",
            "packages/agent",
            "--hidden-import",
            "nodeforge_core",
            "--hidden-import",
            "nodeforge_agent",
            "scripts/agent_entrypoint.py",
        ]
    )

    output = f"dist/{APP_NAME}"
    print(f"\nBuilt binary: {output}")
    print(f"Verify with:\n  ./{output} --help")


if __name__ == "__main__":
    main()
