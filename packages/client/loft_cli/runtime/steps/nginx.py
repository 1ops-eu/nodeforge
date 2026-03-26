"""Nginx installation and configuration commands.

IMPORTANT — Fabric sudo() compatibility:
  See bootstrap.py module docstring for details.  Functions here follow
  the same pattern: no shell operators (``&&``, ``|``, ``>``) in command
  strings that will be executed via Fabric's ``sudo()``.

  Site configuration files are written via ``SSH_UPLOAD`` steps (which use
  the ``upload_content()`` method that stages through /tmp) instead of
  shell redirects.  Config validation and reload are separate steps so
  the plan clearly shows each operation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from loft_cli_core.specs.service_schema import NginxSiteBlock


def install_nginx() -> str:
    return "DEBIAN_FRONTEND=noninteractive apt-get install -y nginx"


def enable_nginx() -> str:
    return "systemctl enable --now nginx"


def validate_nginx_config() -> str:
    """Validate nginx configuration (nginx -t)."""
    return "nginx -t"


def reload_nginx_service() -> str:
    """Reload nginx to apply configuration changes."""
    return "systemctl reload nginx"


def remove_default_site() -> str:
    return "rm -f /etc/nginx/sites-enabled/default"


def site_config_path(site: NginxSiteBlock) -> str:
    """Return the target path for a site's nginx configuration file.

    Uses the raw domain name as the filename — standard nginx convention
    (e.g. ``/etc/nginx/sites-available/app.example.com``).
    """
    return f"/etc/nginx/sites-available/{site.domain}"


def site_config_content(site: NginxSiteBlock) -> str:
    """Return the rendered nginx site config content (for plan display and SSH_UPLOAD)."""
    return _render_site_conf(site)


def enable_site(site: NginxSiteBlock) -> str:
    """Create the symlink from sites-enabled to sites-available.

    Uses the raw domain name as the filename — standard nginx convention.
    """
    return f"ln -sf /etc/nginx/sites-available/{site.domain} /etc/nginx/sites-enabled/{site.domain}"


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
