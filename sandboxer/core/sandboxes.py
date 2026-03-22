"""Sandbox lifecycle orchestration — ties together docker, templates, and agents."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config import SANDBOX_NAME_PREFIX, GlobalConfig
from .docker import (
    CONTAINER_HOME,
    CONTAINER_WORKSPACE,
    LABEL_AGENT,
    LABEL_TEMPLATE,
    LABEL_WORKSPACE,
    build_template as docker_build,
    create as docker_create,
    exec_shell as docker_exec_shell,
    get_runtime,
    is_gvisor_available,
    list_sandboxes as docker_list,
    remove as docker_remove,
    sandbox_stats as docker_sandbox_stats,
    save_as_template as docker_save_as_template,
    stop as docker_stop,
)
from .models import AgentProfile, SandboxInfo, SandboxStats, SandboxTemplate
from .templates import render_dockerfile


def _sandbox_name(template: str, agent: str) -> str:
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"{SANDBOX_NAME_PREFIX}{template}-{agent}-{ts}"


def _build_image(
    template: SandboxTemplate,
    agent: AgentProfile,
    *,
    dns: str | None = None,
) -> str:
    """Build the template Dockerfile and return the image tag.

    If the template doesn't specify an agent_type but the agent profile
    does, the agent's type is used so the agent CLI gets installed.

    If no customizations are needed, the base image is returned directly.
    """
    # Use the agent's type if the template doesn't specify one.
    effective_template = template
    if not template.agent_type and agent.agent_type:
        effective_template = template.model_copy(
            update={"agent_type": agent.agent_type}
        )

    needs_build = bool(
        effective_template.packages
        or effective_template.pip_packages
        or effective_template.npm_packages
        or effective_template.agent_type
        or effective_template.custom_dockerfile_lines
    )
    if not needs_build:
        return effective_template.base_image

    import tempfile

    tag = f"sandboxer/{template.name}-{agent.agent_type}:latest"
    dockerfile_content = render_dockerfile(effective_template)

    with tempfile.TemporaryDirectory() as tmpdir:
        df_path = Path(tmpdir) / "Dockerfile"
        df_path.write_text(dockerfile_content)
        docker_build(str(df_path), tag, context_dir=tmpdir, dns=dns)

    return tag


def create_sandbox(
    template: SandboxTemplate,
    agent: AgentProfile,
    workspace: str,
    *,
    name: str | None = None,
    config: GlobalConfig | None = None,
    ttl_seconds: int | None = None,
    idle_timeout_seconds: int | None = None,
) -> SandboxInfo:
    """Create a new sandbox from a template + agent profile."""
    config = config or GlobalConfig.load()
    sandbox_name = name or _sandbox_name(template.name, agent.name)

    image = _build_image(template, agent, dns=config.dns_server)

    # Build volume mounts: workspace + optional auth dir.
    volumes: dict[str, str] = {}
    resolved_workspace = str(Path(workspace).resolve())
    ws_mount = f"{CONTAINER_WORKSPACE}:ro" if template.read_only_workspace else CONTAINER_WORKSPACE
    volumes[resolved_workspace] = ws_mount

    if agent.auth_dir:
        resolved_auth = str(Path(agent.auth_dir).expanduser().resolve())
        # Mount at the matching dotdir inside the container home.
        # e.g. ~/.codex → /home/agent/.codex
        auth_dirname = Path(agent.auth_dir).name
        volumes[resolved_auth] = f"{CONTAINER_HOME}/{auth_dirname}"

    # Labels for identification and listing.
    labels = {
        LABEL_AGENT: agent.agent_type,
        LABEL_TEMPLATE: template.name,
        LABEL_WORKSPACE: resolved_workspace,
    }

    # Initialize the container backend from config if not already set.
    import containerkit
    from .docker import _runtime as _current_runtime
    if _current_runtime is None:
        import sandboxer.core.docker as _docker_mod
        _docker_mod._runtime = containerkit.resolve(config.container_backend)

    # Use gVisor if available (Docker only), otherwise fall back to default runtime.
    rt = get_runtime()
    runtime = config.container_runtime
    if runtime == "runsc" and (rt.name != "docker" or not is_gvisor_available()):
        runtime = None

    docker_create(
        image,
        name=sandbox_name,
        volumes=volumes,
        labels=labels,
        runtime=runtime,
        network=template.network if template.network != "bridge" else None,
        dns=config.dns_server,
    )

    # Start credential proxy (best-effort).
    proxy_url: str | None = None
    if agent.api_key_env_var:
        try:
            from .proxy_manager import get_proxy_manager

            pm = get_proxy_manager()
            proxy_url = pm.start_proxy(
                sandbox_name, [agent], port=config.credential_proxy_port
            )
        except Exception:
            pass

    # Metadata for auto-cleanup.
    resolved_ttl = ttl_seconds if ttl_seconds is not None else config.default_ttl_seconds
    resolved_idle = (
        idle_timeout_seconds
        if idle_timeout_seconds is not None
        else config.default_idle_timeout_seconds
    )
    if resolved_ttl is not None or resolved_idle is not None:
        try:
            from .metadata import SandboxMetadata, save_metadata

            now = datetime.now()
            meta = SandboxMetadata(
                name=sandbox_name,
                created_at=now,
                last_activity=now,
                ttl_seconds=resolved_ttl,
                idle_timeout_seconds=resolved_idle,
            )
            save_metadata(meta)
        except Exception:
            pass

    return SandboxInfo(
        name=sandbox_name,
        template=template.name,
        agent=agent.name,
        workspace=workspace,
        status="running",
        created_at=datetime.now(),
        credential_proxy_url=proxy_url,
    )


def list_running_sandboxes() -> list[SandboxInfo]:
    """List containers managed by sandboxer."""
    rows = docker_list()
    results: list[SandboxInfo] = []
    for row in rows:
        results.append(
            SandboxInfo(
                name=row.name,
                status=row.status,
                agent=row.agent,
                workspace=row.workspace,
            )
        )
    return results


def stop_sandbox(name: str) -> None:
    docker_stop(name)
    try:
        from .proxy_manager import get_proxy_manager
        get_proxy_manager().stop_proxy(name)
    except Exception:
        pass


def remove_sandbox(name: str) -> None:
    docker_remove(name)
    try:
        from .proxy_manager import get_proxy_manager
        get_proxy_manager().stop_proxy(name)
    except Exception:
        pass
    try:
        from .metadata import delete_metadata
        delete_metadata(name)
    except Exception:
        pass


def _proxy_env(name: str) -> dict[str, str]:
    """Build proxy env vars for a sandbox if a proxy is running."""
    try:
        from .proxy_manager import get_proxy_manager
        pm = get_proxy_manager()
        url = pm.get_proxy_url(name)
        if url:
            return {"HTTP_PROXY": url, "HTTPS_PROXY": url}
    except Exception:
        pass
    return {}


def shell_into(name: str) -> None:
    try:
        from .metadata import touch_activity
        touch_activity(name)
    except Exception:
        pass
    env = {"HOME": CONTAINER_HOME}
    env.update(_proxy_env(name))
    docker_exec_shell(name, env=env, workdir=CONTAINER_WORKSPACE)


def get_sandbox_stats(name: str) -> SandboxStats:
    """Get resource usage stats for a sandbox."""
    data = docker_sandbox_stats(name)
    return SandboxStats(**data)


def snapshot_sandbox(name: str, tag: str) -> None:
    """Commit the current state of a sandbox as a Docker image."""
    docker_save_as_template(name, tag)
