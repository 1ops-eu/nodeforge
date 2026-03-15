"""Local SSH key management — ensure admin key pairs exist before applying."""
from __future__ import annotations

import subprocess
from pathlib import Path

from nodeforge.utils.files import expand_path


def ensure_admin_keys(spec, console=None) -> None:
    """Generate SSH key pairs for any admin pubkeys whose private key is absent.

    Only runs when the auth method is key-based (pubkeys list is non-empty).
    Skips any pubkey path that doesn't follow the conventional '<name>.pub'
    pattern, since we can't safely derive the private key path from it.

    Root's login key is assumed to exist when private_key auth is used — we
    never auto-generate it here.
    """
    for pubkey_path_str in spec.admin_user.pubkeys:
        pub_path = expand_path(pubkey_path_str)

        if pub_path.suffix != ".pub":
            continue  # can't derive private key path — skip

        priv_path = pub_path.with_suffix("")

        if priv_path.exists():
            continue  # key already exists — nothing to do

        # Generate the key pair
        pub_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-f", str(priv_path), "-N", ""],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to generate SSH key pair at {priv_path}: "
                f"{e.stderr.decode().strip()}"
            ) from e

        if console:
            console.print(
                f"[green]✓ Generated SSH key pair:[/green] {priv_path}"
            )
