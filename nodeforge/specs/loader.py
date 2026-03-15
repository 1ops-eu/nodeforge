"""Load and parse YAML specs into typed Pydantic models."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


class SpecLoadError(Exception):
    """Raised when a spec file cannot be loaded or parsed."""


def _resolve_env_vars(obj):
    """Recursively resolve ${VAR} patterns from environment variables."""
    if isinstance(obj, str):
        def replace(m):
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                raise SpecLoadError(
                    f"Environment variable '{var}' is not set (required by spec)"
                )
            return val
        return _ENV_PATTERN.sub(replace, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj


def load_spec(path: Path) -> Any:
    """Load and parse a YAML spec file into a typed model."""
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import load_addons, get_spec_model, list_spec_kinds
    load_addons()

    if not path.exists():
        raise SpecLoadError(f"Spec file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SpecLoadError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise SpecLoadError(f"Spec file must be a YAML mapping, got {type(raw).__name__}")

    kind = raw.get("kind")
    model_class = get_spec_model(kind)
    if model_class is None:
        known = ", ".join(list_spec_kinds()) or "none"
        raise SpecLoadError(
            f"Unknown spec kind '{kind}'. Supported: {known}"
        )

    try:
        data = _resolve_env_vars(raw)
    except SpecLoadError:
        raise

    try:
        return model_class.model_validate(data)
    except ValidationError as e:
        raise SpecLoadError(f"Spec validation error in {path}:\n{e}") from e
