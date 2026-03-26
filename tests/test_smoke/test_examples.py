"""Smoke tests — validate, plan, and docs for all example specs.

These tests run the full pipeline (parse → validate → normalize → plan → docs)
against every example spec in the repository.  They catch regressions in:

- Schema changes that break existing examples
- Planner changes that produce invalid plans
- Normalizer assumptions about paths/defaults

Examples that use ``${env:VAR}`` tokens are run in passthrough mode
(strict_env=False) so unresolved variables don't cause failures.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# ------------------------------------------------------------------ #
# Discovery
# ------------------------------------------------------------------ #

EXAMPLES_ROOT = Path(__file__).resolve().parent.parent.parent / "examples"

# Specs that use ${env:...} tokens — must be run with strict_env=False
_ENV_VAR_SPECS = {
    "bootstrap-env-vars.yaml",
    "bootstrap-password-login.yaml",
}

# Non-spec YAML files in examples/ that should not be parsed as loft-cli specs
# (e.g. agent policy configs, plain config examples)
_NON_SPEC_FILES = {
    "policy.yaml",
}


def _discover_example_specs() -> list[Path]:
    """Return all .yaml spec files under examples/, excluding goss specs and non-spec files."""
    specs = []
    for p in sorted(EXAMPLES_ROOT.rglob("*.yaml")):
        if ".goss." in p.name:
            continue
        if p.name in _NON_SPEC_FILES:
            continue
        specs.append(p)
    return specs


EXAMPLE_SPECS = _discover_example_specs()


def _spec_id(spec_path: Path) -> str:
    """Short ID for parametrize — relative to examples/."""
    return str(spec_path.relative_to(EXAMPLES_ROOT))


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture(params=EXAMPLE_SPECS, ids=[_spec_id(p) for p in EXAMPLE_SPECS])
def example_spec(request) -> Path:
    return request.param


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #


class TestSmokeValidate:
    """Every example spec must parse and validate without errors."""

    def test_parse_and_validate(self, example_spec: Path):
        from loft_cli.compiler.parser import parse
        from loft_cli_core.specs.validators import validate_spec

        strict = example_spec.name not in _ENV_VAR_SPECS
        spec = parse(example_spec, strict_env=strict)
        issues = validate_spec(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors, f"Validation errors in {example_spec.name}: {errors}"


class TestSmokePlan:
    """Every example spec must produce a non-empty plan."""

    def test_plan_produces_steps(self, example_spec: Path):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.parser import parse
        from loft_cli.compiler.planner import plan

        strict = example_spec.name not in _ENV_VAR_SPECS
        spec = parse(example_spec, strict_env=strict)
        ctx = normalize(spec, spec_dir=example_spec.parent)
        ctxs = ctx if isinstance(ctx, list) else [ctx]
        for c in ctxs:
            p = plan(c)
            assert len(p.steps) > 0, f"Plan for {example_spec.name} has no steps"


class TestSmokeDocs:
    """Every example spec must render Markdown docs without errors."""

    def test_docs_render(self, example_spec: Path):
        from loft_cli.compiler.normalizer import normalize
        from loft_cli.compiler.parser import parse
        from loft_cli.compiler.planner import plan
        from loft_cli_core.plan.render_markdown import render_markdown

        strict = example_spec.name not in _ENV_VAR_SPECS
        spec = parse(example_spec, strict_env=strict)
        ctx = normalize(spec, spec_dir=example_spec.parent)
        ctxs = ctx if isinstance(ctx, list) else [ctx]
        for c in ctxs:
            p = plan(c)
            md = render_markdown(p)
            assert len(md) > 100, f"Docs for {example_spec.name} suspiciously short"
            assert p.spec_name in md
