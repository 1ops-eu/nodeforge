"""loft-cli built-in addons.

This package contains optional built-in components that ship with loft-cli
but are architecturally separate from the core compiler/runtime pipeline.
Each addon is a self-contained subpackage.

Current built-in addons:
    goss/   -- Goss server-state verification (post-bootstrap)

External addons are distributed as separate Python packages and discovered
at runtime via the 'loft_cli.addons' entry_points group.
"""
