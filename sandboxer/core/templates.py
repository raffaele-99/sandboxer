"""Template CRUD — YAML + Dockerfile on disk."""
from __future__ import annotations

from pathlib import Path

import yaml

from .config import templates_dir
from .models import SandboxTemplate


def _templates_path(base: Path | None = None) -> Path:
    d = templates_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _yaml_path(name: str, base: Path | None = None) -> Path:
    return _templates_path(base) / f"{name}.yml"


def _dockerfile_path(name: str, base: Path | None = None) -> Path:
    return _templates_path(base) / f"{name}.Dockerfile"


# -- CRUD --------------------------------------------------------------------

def save_template(template: SandboxTemplate, base: Path | None = None) -> Path:
    """Write template YAML and generated Dockerfile to disk. Returns the YAML path."""
    path = _yaml_path(template.name, base)
    path.write_text(
        yaml.dump(template.model_dump(), default_flow_style=False),
        encoding="utf-8",
    )
    df_path = _dockerfile_path(template.name, base)
    df_path.write_text(render_dockerfile(template), encoding="utf-8")
    return path


def load_template(name: str, base: Path | None = None) -> SandboxTemplate:
    path = _yaml_path(name, base)
    if not path.exists():
        raise FileNotFoundError(f"template not found: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SandboxTemplate(**data)


def delete_template(name: str, base: Path | None = None) -> None:
    for path in (_yaml_path(name, base), _dockerfile_path(name, base)):
        path.unlink(missing_ok=True)


def list_templates(base: Path | None = None) -> list[SandboxTemplate]:
    d = _templates_path(base)
    templates: list[SandboxTemplate] = []
    for yml in sorted(d.glob("*.yml")):
        try:
            templates.append(load_template(yml.stem, base))
        except Exception:
            continue
    return templates


# -- Dockerfile rendering ----------------------------------------------------

def render_dockerfile(template: SandboxTemplate) -> str:
    """Generate a Dockerfile from a template definition."""
    from .docker import CONTAINER_HOME, CONTAINER_WORKSPACE

    lines: list[str] = [f"FROM {template.base_image}", ""]

    # All installation happens as root.
    lines.append("USER root")
    lines.append("")

    # Create the non-root agent user and workspace directory.
    sudo_pkg = " sudo" if template.allow_sudo else ""
    lines.append(
        f"RUN groupadd -r agent && useradd -r -g agent -m -d {CONTAINER_HOME} -s /bin/bash agent"
        f" && mkdir -p {CONTAINER_WORKSPACE} && chown agent:agent {CONTAINER_WORKSPACE}"
    )
    if template.allow_sudo:
        lines.append("RUN echo 'agent ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers")
    lines.append("")

    if template.packages or sudo_pkg:
        pkg_str = " ".join(template.packages) + sudo_pkg
        lines.append(
            f"RUN apt-get update && DEBIAN_FRONTEND=noninteractive "
            f"apt-get install -y --no-install-recommends {pkg_str.strip()} "
            f"&& rm -rf /var/lib/apt/lists/*"
        )
        lines.append("")

    if template.pip_packages:
        pip_str = " ".join(template.pip_packages)
        lines.append(f"RUN pip install --no-cache-dir {pip_str}")
        lines.append("")

    if template.npm_packages:
        npm_str = " ".join(template.npm_packages)
        lines.append(f"RUN npm install -g {npm_str}")
        lines.append("")

    # Agent adapter lines (inserted after npm_packages, before custom lines).
    if template.agent_type:
        from .adapters import adapter_dockerfile_lines

        adapter_lines = adapter_dockerfile_lines(template.agent_type)
        if adapter_lines:
            for al in adapter_lines:
                lines.append(al)
            lines.append("")

    for custom_line in template.custom_dockerfile_lines:
        lines.append(custom_line)
    if template.custom_dockerfile_lines:
        lines.append("")

    # Switch to the agent user for runtime.
    lines.append(f"USER agent")
    lines.append(f"WORKDIR {CONTAINER_WORKSPACE}")
    lines.append("")

    return "\n".join(lines)


# -- Template marketplace (push/pull) ----------------------------------------

def push_template(
    name: str,
    registry_tag: str,
    base: Path | None = None,
) -> None:
    """Tag and push a template's base image to a registry."""
    from .docker import push_image, tag_image

    tmpl = load_template(name, base)
    tag_image(tmpl.base_image, registry_tag)
    push_image(registry_tag)
    tmpl.registry_source = registry_tag
    save_template(tmpl, base)


def pull_template(
    registry_tag: str,
    local_name: str | None = None,
    base: Path | None = None,
) -> SandboxTemplate:
    """Pull an image from a registry and create a local template."""
    from .docker import pull_image

    pull_image(registry_tag)
    name = local_name or registry_tag.split("/")[-1].split(":")[0]
    tmpl = SandboxTemplate(
        name=name,
        base_image=registry_tag,
        registry_source=registry_tag,
    )
    save_template(tmpl, base)
    return tmpl
