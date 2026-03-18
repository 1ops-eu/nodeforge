"""PyInstaller entrypoint for nodeforge.

This wrapper is used by build_binary.py to produce the standalone executable.
It delegates directly to the Typer app defined in nodeforge.cli.
"""

from nodeforge.cli import app

if __name__ == "__main__":
    app()
