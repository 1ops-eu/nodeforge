"""Tests for multi-document YAML support."""

from nodeforge.specs.loader import load_spec


def test_single_doc_returns_single_spec(tmp_path):
    """A single-document YAML returns a single spec, not a list."""
    spec_file = tmp_path / "single.yaml"
    spec_file.write_text("""\
kind: service

meta:
  name: test-service
  description: Test

host:
  name: test
  address: 1.2.3.4
  os_family: debian

login:
  user: root
  private_key: ~/.ssh/id_ed25519
  port: 22

local:
  inventory:
    enabled: false

checks: []
""")

    result = load_spec(spec_file)
    assert not isinstance(result, list)
    assert result.kind == "service"


def test_multi_doc_returns_list(tmp_path):
    """A multi-document YAML returns a list of specs."""
    spec_file = tmp_path / "multi.yaml"
    spec_file.write_text("""\
kind: service

meta:
  name: service-1
  description: First

host:
  name: host1
  address: 1.2.3.4
  os_family: debian

login:
  user: root
  private_key: ~/.ssh/id_ed25519
  port: 22

local:
  inventory:
    enabled: false

checks: []

---

kind: service

meta:
  name: service-2
  description: Second

host:
  name: host2
  address: 5.6.7.8
  os_family: debian

login:
  user: root
  private_key: ~/.ssh/id_ed25519
  port: 22

local:
  inventory:
    enabled: false

checks: []
""")

    result = load_spec(spec_file)
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].meta.name == "service-1"
    assert result[1].meta.name == "service-2"


def test_multi_doc_trailing_separator(tmp_path):
    """Trailing --- with no content doesn't create an extra document."""
    spec_file = tmp_path / "trailing.yaml"
    spec_file.write_text("""\
kind: service

meta:
  name: test
  description: Test

host:
  name: test
  address: 1.2.3.4
  os_family: debian

login:
  user: root
  private_key: ~/.ssh/id_ed25519
  port: 22

local:
  inventory:
    enabled: false

checks: []

---
""")

    result = load_spec(spec_file)
    # Single doc with trailing --- should return single spec, not list
    assert not isinstance(result, list)
    assert result.meta.name == "test"
