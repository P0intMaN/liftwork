"""Render a Dockerfile from the bundled Jinja2 templates."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, TemplateNotFound
from jinja2.loaders import DictLoader

from liftwork_core.build.language import Language

DEFAULT_TEMPLATES: dict[Language, str] = {
    Language.python: "python.dockerfile.j2",
    Language.node: "node.dockerfile.j2",
    Language.go: "go.dockerfile.j2",
    Language.static: "static.dockerfile.j2",
}


class DockerfileTemplateError(Exception):
    """Raised when no template exists for the requested language."""


def _load_templates() -> dict[str, str]:
    package = files("liftwork_core.build.templates")
    out: dict[str, str] = {}
    for entry in package.iterdir():
        name = entry.name
        if name.endswith(".dockerfile.j2"):
            out[name] = entry.read_text(encoding="utf-8")
    return out


def _make_env() -> Environment:
    return Environment(
        loader=DictLoader(_load_templates()),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,  # noqa: S701 — Dockerfiles are not HTML
    )


def render_dockerfile(
    language: Language,
    *,
    context: dict[str, Any] | None = None,
    output_path: Path | None = None,
) -> str:
    """Render the default Dockerfile for `language`.

    `context` is passed through to Jinja. `output_path` writes the
    rendered text to disk if provided. Returns the rendered string.
    """
    template_name = DEFAULT_TEMPLATES.get(language)
    if template_name is None:
        msg = f"No default Dockerfile template registered for language={language}"
        raise DockerfileTemplateError(msg)

    env = _make_env()
    try:
        template = env.get_template(template_name)
    except TemplateNotFound as exc:
        msg = f"Dockerfile template not found on disk: {template_name}"
        raise DockerfileTemplateError(msg) from exc

    rendered = template.render(**(context or {}))

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")

    return rendered
