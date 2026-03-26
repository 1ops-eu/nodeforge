"""Policy engine for loft-cli.

Enforces ``policy.yaml`` rules against plan steps before execution.
Policy is **inert by default**: if no policy.yaml is present, no checks
run and the agent executes whatever it receives.

Policy actions
--------------
- ``auto_apply`` — step executes without any human intervention (default).
- ``require_approval`` — step requires a valid approval token before execution.
- ``deny`` — step is refused unconditionally.

Approval tokens
---------------
Temporary, one-off approvals for ``require_approval`` steps.  Tokens are
opaque HMAC-SHA256 strings with an expiry timestamp.  The agent validates
them locally — no network round-trip required.

Design principles
-----------------
- Policy is OSS core — auditable by anyone, activated by configuration.
- No policy.yaml → no policy checks → agent executes what it's told.
- Policy is evaluated per-step, not per-plan.
"""

from __future__ import annotations

import fnmatch
import hashlib
import hmac
import time
from enum import StrEnum
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ── Policy actions ────────────────────────────────────────────────────────────


class PolicyAction(StrEnum):
    AUTO_APPLY = "auto_apply"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


# ── Policy rule model ────────────────────────────────────────────────────────


class PolicyRule(BaseModel):
    """A single policy rule matching steps by kind, id pattern, or tags."""

    name: str = ""
    match_kind: str | None = None  # step kind (e.g. "agent_command")
    match_id: str | None = None  # step id glob (e.g. "install_*")
    match_tags: list[str] = Field(default_factory=list)  # any of these tags
    action: PolicyAction = PolicyAction.AUTO_APPLY


class PolicyConfig(BaseModel):
    """Top-level policy configuration loaded from ``policy.yaml``."""

    version: str = "1"
    default_action: PolicyAction = PolicyAction.AUTO_APPLY
    rules: list[PolicyRule] = Field(default_factory=list)


# ── Approval tokens ──────────────────────────────────────────────────────────

# Token format: "{step_id}:{expires_unix}:{hmac_hex}"
# The HMAC key is derived from the agent's state file hash — so tokens
# are scoped to a specific server.

_TOKEN_SEP = ":"


class ApprovalToken(BaseModel):
    """A temporary approval token for a specific step."""

    step_id: str
    expires_at: float  # Unix timestamp
    signature: str


def generate_approval_token(
    step_id: str,
    secret_key: str,
    ttl_seconds: int = 3600,
) -> str:
    """Generate a time-limited HMAC approval token.

    Parameters
    ----------
    step_id:
        The step this token authorises.
    secret_key:
        HMAC key (typically derived from server identity).
    ttl_seconds:
        How long the token is valid (default: 1 hour).

    Returns
    -------
    Opaque token string suitable for passing via ``--approval-token``.
    """
    expires = time.time() + ttl_seconds
    payload = f"{step_id}{_TOKEN_SEP}{expires}"
    sig = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{step_id}{_TOKEN_SEP}{expires}{_TOKEN_SEP}{sig}"


def validate_approval_token(token: str, secret_key: str) -> ApprovalToken | None:
    """Validate an approval token.

    Returns the parsed token if valid and not expired, or ``None``.
    """
    parts = token.split(_TOKEN_SEP, 2)
    if len(parts) != 3:
        return None

    step_id, expires_str, signature = parts
    try:
        expires = float(expires_str)
    except ValueError:
        return None

    # Check expiry
    if time.time() > expires:
        return None

    # Verify HMAC
    payload = f"{step_id}{_TOKEN_SEP}{expires_str}"
    expected = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return None

    return ApprovalToken(step_id=step_id, expires_at=expires, signature=signature)


# ── Policy loading ───────────────────────────────────────────────────────────


def load_policy(path: Any | None = None) -> PolicyConfig | None:
    """Load policy from a YAML file path.

    Returns ``None`` if the path is ``None`` or the file does not exist
    (policy is inert by default).
    """
    if path is None:
        return None

    from pathlib import Path

    p = Path(path) if not isinstance(path, Path) else path
    if not p.exists():
        return None

    text = p.read_text(encoding="utf-8")
    raw = yaml.safe_load(text)
    if raw is None:
        return None

    return PolicyConfig.model_validate(raw)


# ── Policy evaluation ────────────────────────────────────────────────────────


class PolicyDecision(BaseModel):
    """Result of evaluating policy for a single step."""

    action: PolicyAction
    rule_name: str = ""  # which rule matched (empty = default)
    reason: str = ""


def evaluate_step(
    policy: PolicyConfig | None,
    step_id: str,
    step_kind: str,
    step_tags: list[str],
) -> PolicyDecision:
    """Evaluate policy for a single step.

    If policy is ``None`` (no policy.yaml), returns ``auto_apply``.
    """
    if policy is None:
        return PolicyDecision(action=PolicyAction.AUTO_APPLY, reason="No policy configured")

    for rule in policy.rules:
        if _rule_matches(rule, step_id, step_kind, step_tags):
            return PolicyDecision(
                action=rule.action,
                rule_name=rule.name,
                reason=f"Matched rule '{rule.name}'",
            )

    return PolicyDecision(
        action=policy.default_action,
        reason="Default policy action",
    )


def _rule_matches(
    rule: PolicyRule,
    step_id: str,
    step_kind: str,
    step_tags: list[str],
) -> bool:
    """Check if a policy rule matches a step."""
    # All specified conditions must match (AND logic).
    if rule.match_kind is not None and rule.match_kind != step_kind:
        return False
    if rule.match_id is not None and not fnmatch.fnmatch(step_id, rule.match_id):
        return False
    if rule.match_tags and not any(t in step_tags for t in rule.match_tags):
        return False
    # At least one condition must be specified for the rule to match.
    return not (rule.match_kind is None and rule.match_id is None and not rule.match_tags)
