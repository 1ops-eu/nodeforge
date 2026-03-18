"""Tests for YAML spec loading."""

from pathlib import Path
import pytest
from nodeforge.specs.loader import load_spec, SpecLoadError


def test_load_service_spec(service_yaml):
    spec = load_spec(service_yaml)
    from nodeforge.specs.service_schema import ServiceSpec

    assert isinstance(spec, ServiceSpec)
    assert spec.kind == "service"
    assert spec.postgres.version == "16"


def test_load_invalid_yaml(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("{ invalid: yaml: content")
    with pytest.raises(SpecLoadError):
        load_spec(f)
