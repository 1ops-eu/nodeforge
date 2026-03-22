"""Load and parse YAML specs into typed Pydantic models."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

# Matches ${...} tokens — the full token including optional prefix and default.
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
    for _lineno, raw_line in enumerate(text.splitlines(), 1):
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


def _resolve_values(obj: Any, *, strict: bool = True, _path: str = "") -> Any:
    """Recursively resolve ``${[prefix:]key[:-default]}`` tokens in a YAML structure.

    Token syntax
    ------------
    ``${VAR}``
        Bare reference — shorthand for ``${env:VAR}``.  Permanent backward
        compat; will never be deprecated.

    ``${env:VAR}``
        Explicit environment variable lookup via the ``env`` resolver.

    ``${file:/path/to/file}``
        Read file contents via the built-in ``file`` resolver.

    ``${prefix:key}``
        Dispatch to an addon-registered resolver (e.g. ``sops``, ``vault``).

    ``${VAR:-default}``
        Use *default* if the resolved value is ``None`` (key not found).
        Works with any prefix: ``${env:VAR:-fallback}``,
        ``${file:/opt/key.pub:-}`` etc.

    Parameters
    ----------
    obj:
        The parsed YAML data (nested dicts, lists, scalars).
    strict:
        When ``True`` (default), raise :class:`SpecLoadError` if a token
        cannot be resolved and has no default value.  When ``False``
        ("passthrough"), leave the ``${...}`` token unchanged.
    _path:
        Internal — tracks the YAML field path for error messages.
    """
    if isinstance(obj, str):
        # Import lazily so this function stays usable before load_addons() runs.
        from nodeforge.registry.resolvers import get_resolver, list_resolvers

        def replace(m: re.Match) -> str:
            token = m.group(1)
            location = f" in field '{_path}'" if _path else ""

            # 1. Split off default value (shell convention: :-)
            if ":-" in token:
                ref_part, default = token.split(":-", 1)
            else:
                ref_part, default = token, None

            # 2. Extract prefix (first colon in ref_part).
            #    No colon → bare ${VAR} → permanent shorthand for ${env:VAR}.
            if ":" in ref_part:
                prefix, key = ref_part.split(":", 1)
            else:
                prefix, key = "env", ref_part

            # 3. Resolve via registry.
            resolver = get_resolver(prefix)
            if resolver is None:
                known = ", ".join(list_resolvers()) or "none"
                raise SpecLoadError(
                    f"Unknown resolver '{prefix}' in '${{{token}}}'{location}. "
                    f"Registered resolvers: {known}. "
                    f"Is an addon missing?"
                )

            val = resolver(key)

            # 4. Value found — return it.
            if val is not None:
                return val

            # 5. Value not found — try default.
            if default is not None:
                return default

            # 6. No default — strict vs passthrough.
            if strict:
                raise SpecLoadError(
                    f"Unresolved variable '${{{token}}}'{location}: "
                    f"resolver '{prefix}' returned no value for key '{key}'"
                )
            return m.group(0)  # passthrough: leave ${...} unchanged

        return _ENV_PATTERN.sub(replace, obj)
    elif isinstance(obj, dict):
        return {
            k: _resolve_values(v, strict=strict, _path=f"{_path}.{k}" if _path else k)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [
            _resolve_values(item, strict=strict, _path=f"{_path}[{i}]")
            for i, item in enumerate(obj)
        ]
    return obj


# Keep the old name available so any code that imported _resolve_env_vars
# directly (e.g. existing tests) continues to work without change.
_resolve_env_vars = _resolve_values


def load_spec(path: Path, *, strict_env: bool = True, env_file: Path | None = None) -> Any:
    """Load and parse a YAML spec file into a typed model.

    Parameters
    ----------
    path:
        Path to the YAML spec file.
    strict_env:
        When True (default), unresolved ``${...}`` references raise an error.
        When False, they are left unchanged (passthrough mode).
    env_file:
        Optional path to a ``.env`` file.  Variables defined in it are
        loaded into ``os.environ`` *before* resolving the spec, but only
        for variables that are not already set (existing env vars take
        precedence).
    """
    # Ensure built-in and addon kinds are registered (idempotent).
    from nodeforge.registry import get_spec_model, list_spec_kinds, load_addons

    load_addons()

    if not path.exists():
        raise SpecLoadError(f"Spec file not found: {path}")

    # Load .env file if provided (existing env vars take precedence).
    if env_file is not None:
        if not env_file.exists():
            raise SpecLoadError(f"Env file not found: {env_file}")
        for key, value in load_env_file(env_file).items():
            os.environ.setdefault(key, value)

    text = path.read_text(encoding="utf-8")

    # Support multiple YAML documents separated by ---
    try:
        documents = list(yaml.safe_load_all(text))
    except yaml.YAMLError as e:
        raise SpecLoadError(f"YAML parse error in {path}: {e}") from e

    # Filter out empty documents (e.g. trailing ---)
    documents = [d for d in documents if d is not None]

    if not documents:
        raise SpecLoadError(f"Spec file is empty: {path}")

    specs = []
    for doc_idx, raw in enumerate(documents):
        if not isinstance(raw, dict):
            raise SpecLoadError(
                f"Document {doc_idx + 1} in {path} must be a YAML mapping, "
                f"got {type(raw).__name__}"
            )

        kind = raw.get("kind")
        model_class = get_spec_model(kind)
        if model_class is None:
            known = ", ".join(list_spec_kinds()) or "none"
            raise SpecLoadError(
                f"Unknown spec kind '{kind}' in document {doc_idx + 1}. Supported: {known}"
            )

        try:
            data = _resolve_values(raw, strict=strict_env)
        except SpecLoadError:
            raise

        try:
            specs.append(model_class.model_validate(data))
        except Exception as e:
            if type(e).__name__ == "ValidationError":
                raise SpecLoadError(
                    f"Spec validation error in {path} (document {doc_idx + 1}):\n{e}"
                ) from e
            raise

    # Return single spec for backward compatibility, list for multi-doc
    if len(specs) == 1:
        return specs[0]
    return specs
