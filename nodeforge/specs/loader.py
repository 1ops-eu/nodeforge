"""Load and parse YAML specs into typed Pydantic models."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


class SpecLoadError(Exception):
    """Raised when a spec file cannot be loaded or parsed."""


def load_env_file(path: Path) -> dict[str, str]:
    """Load a .env file and return a dict of variable name → value.

    Supports:
    - Lines of the form ``KEY=VALUE`` or ``KEY="VALUE"`` / ``KEY='VALUE'``
    - ``export KEY=VALUE``
    - Comments (lines starting with ``#``)
    - Blank lines (ignored)

    Does NOT modify ``os.environ``; the caller is responsible for that.
    """
    env: dict[str, str] = {}
    text = path.read_text(encoding="utf-8")
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        # Strip optional 'export ' prefix
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip matching quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


def _resolve_env_vars(obj: Any, *, strict: bool = True, _path: str = "") -> Any:
    """Recursively resolve ``${VAR}`` patterns from environment variables.

    Parameters
    ----------
    obj:
        The parsed YAML data (nested dicts, lists, scalars).
    strict:
        When True (default), raise :class:`SpecLoadError` if a referenced
        variable is not set.  When False ("passthrough"), leave the ``${VAR}``
        token unchanged.
    _path:
        Internal — tracks the YAML field path for error messages.
    """
    if isinstance(obj, str):

        def replace(m: re.Match) -> str:
            var = m.group(1)
            val = os.environ.get(var)
            if val is None:
                if strict:
                    location = f" in field '{_path}'" if _path else ""
                    raise SpecLoadError(
                        f"Unresolved variable '${{{var}}}'{location}: "
                        f"environment variable '{var}' is not set"
                    )
                return m.group(0)  # passthrough: leave ${VAR} unchanged
            return val

        return _ENV_PATTERN.sub(replace, obj)
    elif isinstance(obj, dict):
        return {
            k: _resolve_env_vars(v, strict=strict, _path=f"{_path}.{k}" if _path else k)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [
            _resolve_env_vars(item, strict=strict, _path=f"{_path}[{i}]")
            for i, item in enumerate(obj)
        ]
    return obj


def load_spec(
    path: Path, *, strict_env: bool = True, env_file: Path | None = None
) -> Any:
    """Load and parse a YAML spec file into a typed model.

    Parameters
    ----------
    path:
        Path to the YAML spec file.
    strict_env:
        When True (default), unresolved ``${VAR}`` references raise an error.
        When False, they are left unchanged (passthrough mode).
    env_file:
        Optional path to a ``.env`` file.  Variables defined in it are
        loaded into ``os.environ`` *before* resolving the spec, but only
        for variables that are not already set (existing env vars take
        precedence).
    """
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import load_addons, get_spec_model, list_spec_kinds

    load_addons()

    if not path.exists():
        raise SpecLoadError(f"Spec file not found: {path}")

    # Load .env file if provided (existing env vars take precedence).
    if env_file is not None:
        if not env_file.exists():
            raise SpecLoadError(f"Env file not found: {env_file}")
        for key, value in load_env_file(env_file).items():
            os.environ.setdefault(key, value)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise SpecLoadError(f"YAML parse error in {path}: {e}") from e

    if not isinstance(raw, dict):
        raise SpecLoadError(
            f"Spec file must be a YAML mapping, got {type(raw).__name__}"
        )

    kind = raw.get("kind")
    model_class = get_spec_model(kind)
    if model_class is None:
        known = ", ".join(list_spec_kinds()) or "none"
        raise SpecLoadError(f"Unknown spec kind '{kind}'. Supported: {known}")

    try:
        data = _resolve_env_vars(raw, strict=strict_env)
    except SpecLoadError:
        raise

    try:
        return model_class.model_validate(data)
    except Exception as e:
        # Wrap pydantic ValidationError with a friendlier message.
        # Import lazily to keep module importable without pydantic installed
        # (useful for testing _resolve_env_vars / load_env_file in isolation).
        if type(e).__name__ == "ValidationError":
            raise SpecLoadError(f"Spec validation error in {path}:\n{e}") from e
        raise
