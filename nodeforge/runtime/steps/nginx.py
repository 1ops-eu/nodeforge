"""Nginx installation and configuration commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nodeforge.specs.service_schema import NginxSiteBlock


def install_nginx() -> str:
    return (
        "apt-get update -y 2>&1 | tail -3 && "
        "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"
    )


def enable_nginx() -> str:
    return "systemctl enable --now nginx"


def reload_nginx() -> str:
    return "nginx -t && systemctl reload nginx"


def remove_default_site() -> str:
    return "rm -f /etc/nginx/sites-enabled/default"


def write_site_config(site: NginxSiteBlock) -> str:
    """Generate an nginx site configuration as a shell command that writes to disk."""
    conf = _render_site_conf(site)
    escaped = conf.replace("'", "'\\''")
    filename = site.domain.replace(".", "_")
    return (
        f"printf '%s' '{escaped}' > /etc/nginx/sites-available/{filename} && "
        f"ln -sf /etc/nginx/sites-available/{filename} /etc/nginx/sites-enabled/{filename}"
    )


def site_config_content(site: NginxSiteBlock) -> str:
    """Return the rendered nginx site config content (for plan display)."""
    return _render_site_conf(site)


def _render_site_conf(site: NginxSiteBlock) -> str:
    """Render an nginx virtual host configuration."""
    upstream = site.upstream or "127.0.0.1"
    upstream_addr = f"{upstream}:{site.upstream_port}"

    lines: list[str] = []

    if site.ssl and site.listen_port == 80:
        # Add HTTP -> HTTPS redirect block
        lines.extend(
            [
                "server {",
                "    listen 80;",
                "    listen [::]:80;",
                f"    server_name {site.domain};",
                "    return 301 https://$host$request_uri;",
                "}",
                "",
            ]
        )
        listen_port = 443
    else:
        listen_port = site.listen_port

    lines.append("server {")

    if site.ssl:
        lines.append(f"    listen {listen_port} ssl;")
        lines.append(f"    listen [::]:{listen_port} ssl;")
    else:
        lines.append(f"    listen {listen_port};")
        lines.append(f"    listen [::]:{listen_port};")

    lines.append(f"    server_name {site.domain};")
    lines.append("")

    if site.ssl:
        lines.append(f"    ssl_certificate {site.ssl_certificate};")
        lines.append(f"    ssl_certificate_key {site.ssl_certificate_key};")
        lines.append("    ssl_protocols TLSv1.2 TLSv1.3;")
        lines.append("    ssl_ciphers HIGH:!aNULL:!MD5;")
        lines.append("")

    lines.extend(
        [
            "    location / {",
            f"        proxy_pass http://{upstream_addr};",
            "        proxy_set_header Host $host;",
            "        proxy_set_header X-Real-IP $remote_addr;",
            "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
            "        proxy_set_header X-Forwarded-Proto $scheme;",
            "    }",
            "}",
        ]
    )

    return "\n".join(lines) + "\n"


def nginx_ready_check() -> str:
    return "nginx -t"
