"""Tests for YAML spec loading."""

import pytest

from nodeforge_core.specs.loader import SpecLoadError, load_spec


def test_load_service_spec(service_yaml):
    spec = load_spec(service_yaml)
    from nodeforge_core.specs.service_schema import ServiceSpec

    assert isinstance(spec, ServiceSpec)
    assert spec.kind == "service"
    assert spec.postgres.version == "16"


def test_load_invalid_yaml(tmp_path):
    f = tmp_path / "bad.yaml"
    f.write_text("{ invalid: yaml: content")
    with pytest.raises(SpecLoadError):
        load_spec(f)
