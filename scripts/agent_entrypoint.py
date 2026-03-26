"""PyInstaller entrypoint for loft-cli-agent.

This wrapper is used by build_agent_binary.py to produce the standalone
agent executable.  It delegates directly to the Typer app defined in
loft_cli_agent.cli.
"""

from loft_cli_agent.cli import app

if __name__ == "__main__":
    app()
