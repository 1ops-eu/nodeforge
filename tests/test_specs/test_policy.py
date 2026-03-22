"""Tests for the policy engine (core/policy.py)."""

import time

from nodeforge_core.policy import (
    PolicyAction,
    PolicyConfig,
    PolicyRule,
    evaluate_step,
    generate_approval_token,
    load_policy,
    validate_approval_token,
)

# ── PolicyConfig model ───────────────────────────────────────────────────────


class TestPolicyConfig:
    def test_default_config(self):
        cfg = PolicyConfig()
        assert cfg.version == "1"
        assert cfg.default_action == PolicyAction.AUTO_APPLY
        assert cfg.rules == []

    def test_config_with_rules(self):
        cfg = PolicyConfig(
            default_action=PolicyAction.DENY,
            rules=[
                PolicyRule(
                    name="allow installs",
                    match_id="install_*",
                    action=PolicyAction.AUTO_APPLY,
                ),
            ],
        )
        assert cfg.default_action == PolicyAction.DENY
        assert len(cfg.rules) == 1
        assert cfg.rules[0].name == "allow installs"


# ── evaluate_step ────────────────────────────────────────────────────────────


class TestEvaluateStep:
    def test_no_policy_returns_auto_apply(self):
        decision = evaluate_step(None, "install_docker", "ssh_command", ["docker"])
        assert decision.action == PolicyAction.AUTO_APPLY

    def test_default_action_when_no_rules_match(self):
        policy = PolicyConfig(default_action=PolicyAction.DENY, rules=[])
        decision = evaluate_step(policy, "install_docker", "ssh_command", ["docker"])
        assert decision.action == PolicyAction.DENY

    def test_match_by_id_glob(self):
        policy = PolicyConfig(
            rules=[
                PolicyRule(
                    name="deny installs",
                    match_id="install_*",
                    action=PolicyAction.DENY,
                ),
            ]
        )
        decision = evaluate_step(policy, "install_docker", "ssh_command", [])
        assert decision.action == PolicyAction.DENY
        assert decision.rule_name == "deny installs"

    def test_match_by_kind(self):
        policy = PolicyConfig(
            rules=[
                PolicyRule(
                    name="approve ssh",
                    match_kind="ssh_command",
                    action=PolicyAction.REQUIRE_APPROVAL,
                ),
            ]
        )
        decision = evaluate_step(policy, "some_step", "ssh_command", [])
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_match_by_tags(self):
        policy = PolicyConfig(
            rules=[
                PolicyRule(
                    name="deny hardening",
                    match_tags=["hardening"],
                    action=PolicyAction.DENY,
                ),
            ]
        )
        decision = evaluate_step(policy, "disable_root_login", "ssh_command", ["ssh", "hardening"])
        assert decision.action == PolicyAction.DENY

    def test_no_match_falls_to_default(self):
        policy = PolicyConfig(
            default_action=PolicyAction.AUTO_APPLY,
            rules=[
                PolicyRule(
                    name="deny hardening",
                    match_tags=["hardening"],
                    action=PolicyAction.DENY,
                ),
            ],
        )
        decision = evaluate_step(policy, "apt_update", "ssh_command", ["packages"])
        assert decision.action == PolicyAction.AUTO_APPLY

    def test_first_matching_rule_wins(self):
        policy = PolicyConfig(
            rules=[
                PolicyRule(
                    name="require approval for installs",
                    match_id="install_*",
                    action=PolicyAction.REQUIRE_APPROVAL,
                ),
                PolicyRule(
                    name="deny all",
                    match_id="*",
                    action=PolicyAction.DENY,
                ),
            ]
        )
        decision = evaluate_step(policy, "install_docker", "ssh_command", [])
        assert decision.action == PolicyAction.REQUIRE_APPROVAL

    def test_rule_with_no_conditions_does_not_match(self):
        """A rule with no match_kind, match_id, or match_tags should never match."""
        policy = PolicyConfig(
            default_action=PolicyAction.AUTO_APPLY,
            rules=[
                PolicyRule(name="empty rule", action=PolicyAction.DENY),
            ],
        )
        decision = evaluate_step(policy, "any_step", "ssh_command", ["any"])
        assert decision.action == PolicyAction.AUTO_APPLY


# ── Approval tokens ──────────────────────────────────────────────────────────


class TestApprovalTokens:
    SECRET = "test-secret-key-abc123"

    def test_generate_and_validate_token(self):
        token = generate_approval_token("install_docker", self.SECRET, ttl_seconds=60)
        result = validate_approval_token(token, self.SECRET)
        assert result is not None
        assert result.step_id == "install_docker"
        assert result.expires_at > time.time()

    def test_expired_token_is_rejected(self):
        token = generate_approval_token("install_docker", self.SECRET, ttl_seconds=-1)
        result = validate_approval_token(token, self.SECRET)
        assert result is None

    def test_wrong_secret_is_rejected(self):
        token = generate_approval_token("install_docker", self.SECRET, ttl_seconds=60)
        result = validate_approval_token(token, "wrong-secret")
        assert result is None

    def test_malformed_token_is_rejected(self):
        assert validate_approval_token("garbage", self.SECRET) is None
        assert validate_approval_token("a:b", self.SECRET) is None
        assert validate_approval_token("", self.SECRET) is None

    def test_tampered_token_is_rejected(self):
        token = generate_approval_token("install_docker", self.SECRET, ttl_seconds=60)
        parts = token.split(":", 2)
        parts[2] = "0" * len(parts[2])  # replace signature
        tampered = ":".join(parts)
        result = validate_approval_token(tampered, self.SECRET)
        assert result is None


# ── load_policy ──────────────────────────────────────────────────────────────


class TestLoadPolicy:
    def test_load_none_returns_none(self):
        assert load_policy(None) is None

    def test_load_missing_file_returns_none(self, tmp_path):
        assert load_policy(tmp_path / "nonexistent.yaml") is None

    def test_load_valid_policy_file(self, tmp_path):
        policy_file = tmp_path / "policy.yaml"
        policy_file.write_text("""\
version: "1"
default_action: deny
rules:
  - name: allow preflight
    match_id: "preflight_*"
    action: auto_apply
""")
        policy = load_policy(policy_file)
        assert policy is not None
        assert policy.default_action == PolicyAction.DENY
        assert len(policy.rules) == 1
        assert policy.rules[0].name == "allow preflight"

    def test_load_empty_yaml_returns_none(self, tmp_path):
        policy_file = tmp_path / "empty.yaml"
        policy_file.write_text("")
        assert load_policy(policy_file) is None
