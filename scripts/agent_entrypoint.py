"""PyInstaller entrypoint for nodeforge-agent.

This wrapper is used by build_agent_binary.py to produce the standalone
agent executable.  It delegates directly to the Typer app defined in
nodeforge_agent.cli.
"""

from nodeforge_agent.cli import app

if __name__ == "__main__":
    app()
