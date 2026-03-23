"""Value resolver registry: maps prefix strings to resolution backends.

A resolver callable has the signature:

    (key: str) -> str | None

Returns the resolved string value, or ``None`` if the key was not found /
is unset.  The caller (``_resolve_values`` in ``specs/loader.py``) is
responsible for handling the ``None`` case — applying the default value
if provided, raising a ``SpecLoadError`` in strict mode, or leaving the
``${...}`` token unchanged in passthrough mode.

Built-in resolvers registered at startup by ``_builtins._register_resolvers()``:

* ``env``  — looks up ``os.environ`` (identical behaviour to the original
  ``${VAR}`` syntax; bare ``${VAR}`` without a prefix is permanent shorthand
  for ``${env:VAR}``)
* ``file`` — reads the file at the given path and returns its contents with
  a single trailing newline stripped.  Paths are resolved relative to the
  current working directory; ``~`` is expanded.

External addons register additional resolvers (e.g. ``sops``, ``vault``) the
same way they register all other extensions — via a ``register()`` function
declared as a ``nodeforge.addons`` entry point:

    from nodeforge_core.registry import register_resolver

    def register():
        register_resolver("sops", _resolve_sops)

    def _resolve_sops(key: str) -> str | None:
        # key format: "path/to/secrets.yaml#json.dot.path"
        ...
"""

from __future__ import annotations

from collections.abc import Callable

_RESOLVER_REGISTRY: dict[str, Callable[[str], str | None]] = {}


def register_resolver(prefix: str, fn: Callable[[str], str | None]) -> None:
    """Register a value resolver for the given prefix string.

    Parameters
    ----------
    prefix:
        The prefix used inside ``${prefix:key}`` tokens in spec files.
        Registering an existing prefix replaces the previous resolver.
    fn:
        Callable with signature ``(key: str) -> str | None``.
        Return the resolved string value, or ``None`` if not found.
    """
    _RESOLVER_REGISTRY[prefix] = fn


def get_resolver(prefix: str) -> Callable[[str], str | None] | None:
    """Return the resolver for the given prefix, or ``None`` if not registered."""
    return _RESOLVER_REGISTRY.get(prefix)


def list_resolvers() -> list[str]:
    """Return a sorted list of all registered resolver prefixes."""
    return sorted(_RESOLVER_REGISTRY.keys())
