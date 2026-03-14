"""Phase 1: Load YAML spec file into a typed model."""
from pathlib import Path
from typing import Union

from nodeforge.specs.bootstrap_schema import BootstrapSpec
from nodeforge.specs.service_schema import ServiceSpec
from nodeforge.specs.loader import load_spec

AnySpec = Union[BootstrapSpec, ServiceSpec]


def parse(spec_path: Path) -> AnySpec:
    """Load and parse a YAML spec file."""
    return load_spec(spec_path)
