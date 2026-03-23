"""Tests for nginx service kind — schema, validation, steps, and planning."""

import textwrap
from pathlib import Path

import pytest
from pydantic import ValidationError

from nodeforge.runtime.steps.nginx import (
    enable_nginx,
    enable_site,
    install_nginx,
    nginx_ready_check,
    reload_nginx_service,
    remove_default_site,
    site_config_content,
    site_config_path,
    validate_nginx_config,
)
from nodeforge_core.specs.service_schema import (
    NginxBlock,
    NginxSiteBlock,
    ServiceSpec,
)
from nodeforge_core.specs.validators import has_errors, validate_service

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def _make_service_spec(**overrides) -> ServiceSpec:
    base = {
        "kind": "service",
        "meta": {"name": "test", "description": "test"},
        "host": {"name": "n1", "address": "1.2.3.4", "os_family": "debian"},
    }
    base.update(overrides)
    return ServiceSpec.model_validate(base)


class TestNginxSchema:
    def test_nginx_block_defaults(self):
        block = NginxBlock()
        assert block.enabled is True
        assert block.sites == []

    def test_nginx_site_defaults(self):
        site = NginxSiteBlock(domain="example.com")
        assert site.domain == "example.com"
        assert site.upstream == ""
        assert site.upstream_port == 8080
        assert site.listen_port == 80
        assert site.ssl is False
        assert site.ssl_certificate == ""
        assert site.ssl_certificate_key == ""

    def test_nginx_site_custom(self):
        site = NginxSiteBlock(
            domain="app.example.com",
            upstream="10.0.0.5",
            upstream_port=3000,
            listen_port=443,
            ssl=True,
            ssl_certificate="/etc/ssl/certs/app.pem",
            ssl_certificate_key="/etc/ssl/private/app.key",
        )
        assert site.upstream == "10.0.0.5"
        assert site.upstream_port == 3000
        assert site.listen_port == 443
        assert site.ssl is True

    def test_service_spec_with_nginx(self):
        spec = _make_service_spec(
            nginx={
                "enabled": True,
                "sites": [{"domain": "example.com", "upstream_port": 8080}],
            }
        )
        assert spec.nginx is not None
        assert spec.nginx.enabled is True
        assert len(spec.nginx.sites) == 1
        assert spec.nginx.sites[0].domain == "example.com"

    def test_service_spec_without_nginx(self):
        spec = _make_service_spec()
        assert spec.nginx is None

    def test_nginx_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            NginxBlock(enabled=True, unknown_field="bad")

    def test_nginx_site_forbids_extra_fields(self):
        with pytest.raises(ValidationError):
            NginxSiteBlock(domain="example.com", unknown_field="bad")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


class TestNginxValidation:
    def test_nginx_enabled_no_sites_warning(self):
        spec = _make_service_spec(nginx={"enabled": True, "sites": []})
        issues = validate_service(spec)
        warnings = [i for i in issues if i.severity == "warning"]
        assert any("no sites defined" in w.message for w in warnings)

    def test_nginx_site_missing_domain(self):
        spec = _make_service_spec(
            nginx={"enabled": True, "sites": [{"domain": "", "upstream_port": 8080}]}
        )
        issues = validate_service(spec)
        assert has_errors(issues)
        assert any("domain" in i.field for i in issues if i.severity == "error")

    def test_nginx_ssl_without_certs_error(self):
        spec = _make_service_spec(
            nginx={
                "enabled": True,
                "sites": [{"domain": "example.com", "ssl": True}],
            }
        )
        issues = validate_service(spec)
        assert has_errors(issues)
        assert any("ssl" in i.field.lower() for i in issues if i.severity == "error")

    def test_nginx_ssl_with_certs_ok(self):
        spec = _make_service_spec(
            nginx={
                "enabled": True,
                "sites": [
                    {
                        "domain": "example.com",
                        "ssl": True,
                        "ssl_certificate": "/etc/ssl/cert.pem",
                        "ssl_certificate_key": "/etc/ssl/key.pem",
                    }
                ],
            }
        )
        issues = validate_service(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors

    def test_nginx_invalid_listen_port(self):
        spec = _make_service_spec(
            nginx={
                "enabled": True,
                "sites": [{"domain": "example.com", "listen_port": 0}],
            }
        )
        issues = validate_service(spec)
        assert has_errors(issues)
        assert any("listen_port" in i.field for i in issues if i.severity == "error")

    def test_nginx_valid_spec_no_errors(self):
        spec = _make_service_spec(
            nginx={
                "enabled": True,
                "sites": [{"domain": "example.com", "upstream_port": 8080}],
            }
        )
        issues = validate_service(spec)
        errors = [i for i in issues if i.severity == "error"]
        assert not errors


# ---------------------------------------------------------------------------
# Steps (command generation)
# ---------------------------------------------------------------------------


class TestNginxSteps:
    def test_install_nginx(self):
        cmd = install_nginx()
        assert "apt-get" in cmd
        assert "nginx" in cmd

    def test_enable_nginx(self):
        cmd = enable_nginx()
        assert "systemctl" in cmd
        assert "nginx" in cmd

    def test_validate_nginx_config(self):
        cmd = validate_nginx_config()
        assert "nginx -t" in cmd

    def test_reload_nginx_service(self):
        cmd = reload_nginx_service()
        assert "systemctl reload nginx" in cmd

    def test_remove_default_site(self):
        cmd = remove_default_site()
        assert "sites-enabled/default" in cmd

    def test_site_config_path(self):
        site = NginxSiteBlock(domain="app.example.com", upstream_port=3000)
        path = site_config_path(site)
        assert "sites-available/app.example.com" in path

    def test_enable_site(self):
        site = NginxSiteBlock(domain="app.example.com", upstream_port=3000)
        cmd = enable_site(site)
        assert "ln -sf" in cmd
        assert "sites-available/app.example.com" in cmd
        assert "sites-enabled/app.example.com" in cmd

    def test_site_config_content_basic(self):
        site = NginxSiteBlock(domain="app.example.com", upstream_port=3000)
        conf = site_config_content(site)
        assert "server_name app.example.com" in conf
        assert "listen 80" in conf
        assert "proxy_pass http://127.0.0.1:3000" in conf
        assert "X-Forwarded-For" in conf
        assert "ssl" not in conf.lower() or "ssl" not in conf.split("server_name")[0]

    def test_site_config_content_custom_upstream(self):
        site = NginxSiteBlock(domain="app.example.com", upstream="10.0.0.5", upstream_port=8080)
        conf = site_config_content(site)
        assert "proxy_pass http://10.0.0.5:8080" in conf

    def test_site_config_content_ssl(self):
        site = NginxSiteBlock(
            domain="secure.example.com",
            ssl=True,
            ssl_certificate="/etc/ssl/cert.pem",
            ssl_certificate_key="/etc/ssl/key.pem",
        )
        conf = site_config_content(site)
        assert "ssl_certificate /etc/ssl/cert.pem" in conf
        assert "ssl_certificate_key /etc/ssl/key.pem" in conf
        assert "ssl_protocols TLSv1.2 TLSv1.3" in conf
        assert "443" in conf

    def test_site_config_ssl_with_port_80_adds_redirect(self):
        site = NginxSiteBlock(
            domain="secure.example.com",
            listen_port=80,
            ssl=True,
            ssl_certificate="/etc/ssl/cert.pem",
            ssl_certificate_key="/etc/ssl/key.pem",
        )
        conf = site_config_content(site)
        assert "return 301 https://$host$request_uri" in conf
        assert "listen 443 ssl" in conf

    def test_nginx_ready_check(self):
        cmd = nginx_ready_check()
        assert "nginx -t" in cmd


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


class TestNginxPlanner:
    @pytest.fixture
    def nginx_service_yaml(self, tmp_path) -> Path:
        content = textwrap.dedent("""\
            kind: service
            meta:
              name: nginx-test
              description: Test nginx planning
            host:
              name: test-node-1
              address: 192.168.1.100
              os_family: debian
            login:
              user: admin
              private_key: ~/.ssh/id_ed25519
              port: 2222
            nginx:
              enabled: true
              sites:
                - domain: app.example.com
                  upstream_port: 8080
                - domain: api.example.com
                  upstream: 10.0.0.5
                  upstream_port: 3000
            local:
              inventory:
                enabled: false
            checks: []
        """)
        f = tmp_path / "nginx-service.yaml"
        f.write_text(content)
        return f

    def test_plan_has_nginx_steps(self, nginx_service_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(nginx_service_yaml)
        ctx = normalize(spec)
        p = plan(ctx)

        nginx_steps = [s for s in p.steps if "nginx" in s.tags]
        assert len(nginx_steps) > 0

    def test_plan_has_install_enable_reload(self, nginx_service_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(nginx_service_yaml)
        ctx = normalize(spec)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "install_nginx" in step_ids
        assert "enable_nginx" in step_ids
        assert "remove_nginx_default_site" in step_ids
        assert "validate_nginx_config" in step_ids
        assert "reload_nginx" in step_ids
        assert "nginx_config_check" in step_ids

    def test_plan_has_per_site_steps(self, nginx_service_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(nginx_service_yaml)
        ctx = normalize(spec)
        p = plan(ctx)

        step_ids = [s.id for s in p.steps]
        assert "write_nginx_site_app_example_com" in step_ids
        assert "write_nginx_site_api_example_com" in step_ids
        assert "enable_nginx_site_app_example_com" in step_ids
        assert "enable_nginx_site_api_example_com" in step_ids

    def test_nginx_steps_are_sudo(self, nginx_service_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(nginx_service_yaml)
        ctx = normalize(spec)
        p = plan(ctx)

        nginx_remote = [s for s in p.steps if "nginx" in s.tags and s.scope.value == "remote"]
        for step in nginx_remote:
            assert step.sudo is True, f"Step {step.id} should be sudo"

    def test_step_indices_sequential(self, nginx_service_yaml):
        from nodeforge.compiler.normalizer import normalize
        from nodeforge.compiler.planner import plan
        from nodeforge_core.specs.loader import load_spec

        spec = load_spec(nginx_service_yaml)
        ctx = normalize(spec)
        p = plan(ctx)

        indices = [s.index for s in p.steps]
        assert indices == list(range(len(p.steps)))
