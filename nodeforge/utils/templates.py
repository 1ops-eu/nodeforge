"""Shared Jinja2 template rendering for file_template and compose_project specs.

Templates are rendered at plan time so the rendered content appears in
step.file_content, making plans fully reviewable and deterministic.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from nodeforge.utils.hashing import sha256_string


class TemplateRenderError(Exception):
    """Raised when template rendering fails."""


def render_template_file(
    template_path: Path,
    variables: dict[str, str],
) -> str:
    """Render a Jinja2 template file with the given variables.

    The template is loaded from its parent directory so that Jinja2's
    include/extends directives work with sibling files.

    Args:
        template_path: Absolute path to the Jinja2 template file.
        variables: Key-value pairs passed to the template context.

    Returns:
        The rendered template content as a string.

    Raises:
        TemplateRenderError: If the template cannot be found or rendered.
    """
    if not template_path.exists():
        raise TemplateRenderError(f"Template file not found: {template_path}")

    try:
        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.get_template(template_path.name)
        return template.render(**variables)
    except TemplateNotFound as e:
        raise TemplateRenderError(f"Template not found: {e}") from e
    except Exception as e:
        raise TemplateRenderError(f"Failed to render template '{template_path}': {e}") from e


def render_template_string(
    template_str: str,
    variables: dict[str, str],
) -> str:
    """Render a Jinja2 template string with the given variables.

    Args:
        template_str: Jinja2 template content as a string.
        variables: Key-value pairs passed to the template context.

    Returns:
        The rendered content as a string.

    Raises:
        TemplateRenderError: If the template cannot be rendered.
    """
    try:
        env = Environment(
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            autoescape=False,
        )
        template = env.from_string(template_str)
        return template.render(**variables)
    except Exception as e:
        raise TemplateRenderError(f"Failed to render template string: {e}") from e


def content_hash(content: str) -> str:
    """Return the SHA-256 hash of rendered content for change detection."""
    return sha256_string(content)
