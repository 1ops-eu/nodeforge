"""Agent-based transport implementation.

Turns the client into a thin transporter: uploads the plan to the target
server, invokes the loft-cli-agent, and retrieves the results. Falls back
to direct SSH for bootstrap steps before the agent is installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loft_cli.runtime.fabric_transport import FabricTransport
from loft_cli.runtime.ssh import CommandResult
from loft_cli_core.agent_models import AgentApplyResult
from loft_cli_core.agent_paths import AGENT_BINARY_PATH, AGENT_DESIRED_DIR
from loft_cli_core.plan.models import Plan

if TYPE_CHECKING:
    pass


class AgentTransport:
    """Transport that delegates execution to the server-side agent.

    Uses an underlying FabricTransport for SSH communication (uploading
    plan, invoking agent, downloading results). The agent executes the
    plan locally on the managed server.
    """

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        password: str | None = None,
        key_path: str | None = None,
        connect_timeout: int = 10,
    ) -> None:
        self._ssh = FabricTransport(
            host=host,
            user=user,
            port=port,
            password=password,
            key_path=key_path,
            connect_timeout=connect_timeout,
        )
        self.host = host
        self.user = user
        self.port = port

    def apply_plan(self, plan: Plan) -> AgentApplyResult:
        """Upload plan to target and invoke the agent to execute it.

        Returns the agent's apply result.
        """
        # 1. Ensure desired state directory exists
        self._ssh.run(f"mkdir -p {AGENT_DESIRED_DIR}", sudo=True, warn=True)

        # 2. Upload plan as JSON
        plan_json = plan.model_dump_json(indent=2)
        plan_remote_path = f"{AGENT_DESIRED_DIR}/plan.json"
        self._ssh.upload_content(plan_json, plan_remote_path, sudo=True)

        # 3. Invoke the agent
        result = self._ssh.run(
            f"{AGENT_BINARY_PATH} apply {plan_remote_path}",
            sudo=True,
            warn=True,
        )

        # 4. Retrieve the result file
        result_content = self._ssh.download("/var/lib/loft-cli/last-result.json")

        try:
            return AgentApplyResult.model_validate_json(result_content)
        except Exception:
            # If result file parsing fails, construct from the SSH output
            return AgentApplyResult(
                plan_hash=plan.plan_hash,
                spec_hash=plan.spec_hash,
                step_results=[],
                status="failed" if not result.ok else "success",
                started_at="",
                finished_at="",
                unchanged_count=0,
                applied_count=0,
            )

    # Delegate standard transport methods to the inner SSH transport
    # (used during bootstrap before agent is installed)

    def run(
        self,
        cmd: str,
        sudo: bool = False,
        warn: bool = True,
        hide: bool = True,
    ) -> CommandResult:
        return self._ssh.run(cmd, sudo=sudo, warn=warn, hide=hide)

    def upload(self, local_path: Path | str, remote_path: str) -> None:
        self._ssh.upload(local_path, remote_path)

    def upload_content(self, content: str, remote_path: str, sudo: bool = False) -> CommandResult:
        return self._ssh.upload_content(content, remote_path, sudo=sudo)

    def download(self, remote_path: str) -> str:
        return self._ssh.download(remote_path)

    def test_connection(self) -> bool:
        return self._ssh.test_connection()

    def close(self) -> None:
        self._ssh.close()
