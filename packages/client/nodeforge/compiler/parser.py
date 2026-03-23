"""Phase 1: Load YAML spec file into a typed model."""

from __future__ import annotations

from pathlib import Path

from nodeforge_core.specs.bootstrap_schema import BootstrapSpec
from nodeforge_core.specs.compose_project_schema import ComposeProjectSpec
from nodeforge_core.specs.file_template_schema import FileTemplateSpec
from nodeforge_core.specs.loader import load_spec
from nodeforge_core.specs.service_schema import ServiceSpec
from nodeforge_core.specs.stack_schema import StackSpec

AnySpec = BootstrapSpec | ServiceSpec | FileTemplateSpec | ComposeProjectSpec | StackSpec


def parse(
    spec_path: Path,
    *,
    strict_env: bool = True,
    env_file: Path | None = None,
    env_files: list[Path] | None = None,
) -> AnySpec | list[AnySpec]:
    """Load and parse a YAML spec file.

    Parameters
    ----------
    spec_path:
        Path to the YAML spec file.
    strict_env:
        When True (default), unresolved ``${VAR}`` references raise an error.
        When False, they are left unchanged (passthrough mode).
    env_file:
        Optional path to a single ``.env`` file (backward-compatible).
    env_files:
        Optional list of ``.env`` file paths.  Later files override earlier
        ones; existing ``os.environ`` values always take precedence.

    Returns a single spec for single-document files, or a list of specs
    for multi-document files (separated by ``---``).
    """
    return load_spec(spec_path, strict_env=strict_env, env_file=env_file, env_files=env_files)
