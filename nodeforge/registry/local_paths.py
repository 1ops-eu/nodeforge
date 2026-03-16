"""Addon-overridable local filesystem path configuration.

Core code always calls ``get_local_paths()`` to discover where nodeforge
stores its local state (SSH conf.d entries, WireGuard key material, etc.).
The defaults place everything under standard XDG-adjacent directories:

    ~/.ssh/conf.d/nodeforge/   — per-host SSH config fragments
    ~/.wg/nodeforge/           — per-host WireGuard key material and metadata

Commercial clones or multi-environment addons can override these paths
**without modifying any core source file** by registering a
``LocalPathsConfig`` in their ``register()`` function:

    from nodeforge.registry.local_paths import register_local_paths, LocalPathsConfig
    from pathlib import Path

    def register():
        register_local_paths(LocalPathsConfig(
            ssh_conf_d_base=Path("~/.ssh/conf.d/mycompany/prod/").expanduser(),
            wg_state_base=Path("~/.wg/mycompany/prod/").expanduser(),
        ))

Semantics: last registration wins.  Core calls ``register_local_paths``
once (via ``_builtins._register_builtins``) to set the defaults; addons
loaded afterward simply replace the config object.

Planned: ``nodeforge doctor`` will display the active paths so operators
always know exactly where their local state lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


def _default_ssh_conf_d_base() -> Path:
    return Path("~/.ssh/conf.d/nodeforge").expanduser()


def _default_wg_state_base() -> Path:
    return Path("~/.wg/nodeforge").expanduser()


@dataclass
class LocalPathsConfig:
    """Filesystem base directories for nodeforge local state.

    Attributes
    ----------
    ssh_conf_d_base:
        Directory that contains per-host SSH config fragments.
        Core appends ``{host_name}.conf`` to form the final path.
        The ``Include`` directive written to ``~/.ssh/config`` will be
        ``Include {ssh_conf_d_base}/*``, so all fragments in the directory
        are covered by a single glob — no per-file Include management needed.

    wg_state_base:
        Directory under which per-host WireGuard state is stored.
        Core appends ``{host_name}/`` to form the per-host directory, then
        writes ``private.key``, ``public.key``, ``wg0.conf``, and
        ``metadata.json`` inside it.
    """

    ssh_conf_d_base: Path = field(default_factory=_default_ssh_conf_d_base)
    wg_state_base: Path = field(default_factory=_default_wg_state_base)


# Module-level singleton — replaced wholesale on each call to register_local_paths().
_config: LocalPathsConfig = LocalPathsConfig()


def register_local_paths(config: LocalPathsConfig) -> None:
    """Replace the active local paths config (last registration wins)."""
    global _config
    _config = config


def get_local_paths() -> LocalPathsConfig:
    """Return the currently active local paths config."""
    return _config
