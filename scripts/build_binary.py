"""Binary build script for nodeforge (Linux and macOS only).

Builds a standalone single-file executable using PyInstaller.

Usage:
    python scripts/build_binary.py

Output:
    dist/nodeforge          (Linux / macOS)
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

    # Install all three packages so PyInstaller can resolve imports.
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "packages/core",
            "packages/client",
            "packages/agent",
        ]
    )

    # Build single-file executable.
    # --paths ensures packages are on sys.path for PyInstaller analysis.
    # Hidden imports cover fabric's paramiko/invoke internals which
    # PyInstaller may not detect automatically.
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
            "packages/client",
            "--hidden-import",
            "nodeforge_core",
            "--hidden-import",
            "nodeforge",
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
