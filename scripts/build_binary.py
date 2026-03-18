"""Binary build script for nodeforge (Linux and macOS only).

Builds a standalone single-file executable using PyInstaller.

Usage:
    python scripts/build_binary.py

Output:
    dist/nodeforge          (Linux / macOS)

Prerequisites:
    Linux:   apt-get install libsqlcipher-dev
    macOS:   brew install sqlcipher

Note: The sqlcipher3 dependency requires the SQLCipher shared library to be
present on the build host. The resulting binary links against it dynamically.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

APP_NAME = "nodeforge"


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

    # Build single-file executable.
    # --paths . ensures the root-level nodeforge/ package is on sys.path.
    # Hidden imports cover fabric's paramiko/invoke internals and sqlcipher3
    # C-extension which PyInstaller may not detect automatically.
    run(
        [
            "pyinstaller",
            "--onefile",
            "--name",
            APP_NAME,
            "--clean",
            "--paths",
            ".",
            "--hidden-import",
            "sqlcipher3",
            "--hidden-import",
            "paramiko",
            "--hidden-import",
            "invoke",
            "--hidden-import",
            "fabric",
            "scripts/entrypoint.py",
        ]
    )

    output = f"dist/{APP_NAME}"
    print(f"\nBuilt binary: {output}")
    print(f"Verify with:\n  ./{output} --help")


if __name__ == "__main__":
    main()
