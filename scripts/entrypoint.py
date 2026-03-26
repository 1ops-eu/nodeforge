"""PyInstaller entrypoint for loft-cli.

This wrapper is used by build_binary.py to produce the standalone executable.
It delegates directly to the Typer app defined in loft_cli.cli.
"""

from loft_cli.cli import app

if __name__ == "__main__":
    app()
