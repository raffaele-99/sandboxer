"""Sandbox CRUD routes — full pages and HTMX partials."""
from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import datetime
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response, StreamingResponse
from starlette.routing import Route

from ...core.agents import list_agents, load_agent
from ...core.config import GlobalConfig
from ...core.docker import (
    CONTAINER_HOME,
    CONTAINER_WORKSPACE,
    LABEL_AGENT,
    LABEL_TEMPLATE,
    LABEL_WORKSPACE,
    DockerError,
    build_template_stream,
    create as docker_create,
    get_runtime,
    is_gvisor_available,
)
from ...core.models import SandboxInfo
from ...core.sandboxes import (
    _build_image,
    _sandbox_name,
    create_sandbox,
    get_sandbox_stats,
    list_running_sandboxes,
    remove_sandbox,
    snapshot_sandbox,
    stop_sandbox,
)
from ...core.templates import list_templates, load_template, render_dockerfile


def _error_response(msg: str) -> Response:
    """Return a 422 with a toast error message."""
    import json

    response = Response(status_code=422)
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": msg, "level": "error"}}
    )
    return response


# ---------------------------------------------------------------------------
# Full pages
# ---------------------------------------------------------------------------


async def sandbox_list_page(request: Request) -> HTMLResponse:
    """Full-page sandbox list."""
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    return request.app.state.templates.TemplateResponse(
        request,
        "sandboxes/list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_create_page(request: Request) -> HTMLResponse:
    """Sandbox creation form."""
    templates, agents = await asyncio.gather(
        asyncio.to_thread(list_templates),
        asyncio.to_thread(list_agents),
    )
    return request.app.state.templates.TemplateResponse(
        request,
        "sandboxes/create.html",
        {"templates": templates, "agents": agents, "error": None},
    )


async def sandbox_create(request: Request) -> Response:
    """Handle sandbox creation — redirects to the SSE stream endpoint."""
    form = await request.form()
    template_name = form.get("template", "").strip()
    agent_name = form.get("agent", "").strip()
    workspace = form.get("workspace", ".").strip() or "."
    name = form.get("name", "").strip() or ""
    ttl = form.get("ttl", "").strip()
    idle_timeout = form.get("idle_timeout", "").strip()

    if not template_name or not agent_name:
        return _error_response("Template and agent are required.")

    # Build query string for the SSE endpoint.
    import urllib.parse
    params = {
        "template": template_name,
        "agent": agent_name,
        "workspace": workspace,
    }
    if name:
        params["name"] = name
    if ttl:
        params["ttl"] = ttl
    if idle_timeout:
        params["idle_timeout"] = idle_timeout
    qs = urllib.parse.urlencode(params)

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/sandboxes/create/stream?{qs}"
    return response


async def sandbox_create_stream_page(request: Request) -> HTMLResponse:
    """Page that connects to the SSE stream to show creation progress."""
    return request.app.state.templates.TemplateResponse(
        request,
        "sandboxes/create_progress.html",
        {
            "sse_url": f"/sandboxes/create/events?{request.url.query}",
        },
    )


async def sandbox_create_events(request: Request) -> StreamingResponse:
    """SSE endpoint that streams sandbox creation progress."""

    template_name = request.query_params.get("template", "")
    agent_name = request.query_params.get("agent", "")
    workspace = request.query_params.get("workspace", ".")
    name = request.query_params.get("name", "")
    ttl = request.query_params.get("ttl", "")
    idle_timeout = request.query_params.get("idle_timeout", "")

    async def event_stream():
        def _sse(event: str, data: dict) -> str:
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        try:
            yield _sse("step", {"message": "Loading template and agent..."})
            template = await asyncio.to_thread(load_template, template_name)
            agent = await asyncio.to_thread(load_agent, agent_name)

            config = await asyncio.to_thread(GlobalConfig.load)
            sandbox_name = name or _sandbox_name(template.name, agent.name)

            # Determine if a build is needed.
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

            if needs_build:
                tag = f"sandboxer/{template.name}-{agent.agent_type}:latest"
                yield _sse("step", {"message": f"Building image {tag}..."})

                dockerfile_content = render_dockerfile(effective_template)
                tmpdir = tempfile.mkdtemp()
                df_path = Path(tmpdir) / "Dockerfile"
                df_path.write_text(dockerfile_content)

                proc = await asyncio.to_thread(
                    build_template_stream,
                    str(df_path), tag, context_dir=tmpdir, dns=config.dns_server,
                )

                loop = asyncio.get_running_loop()
                while True:
                    line = await loop.run_in_executor(
                        None, proc.stdout.readline,
                    )
                    if not line:
                        break
                    line = line.rstrip()
                    if line:
                        yield _sse("log", {"message": line})

                await asyncio.to_thread(proc.wait)
                # Clean up temp dir.
                import shutil
                shutil.rmtree(tmpdir, ignore_errors=True)

                if proc.returncode != 0:
                    yield _sse("error", {"message": f"Image build failed (exit {proc.returncode})"})
                    return

                image = tag
                yield _sse("step", {"message": "Image built successfully."})
            else:
                image = effective_template.base_image
                yield _sse("step", {"message": f"Using existing image {image}"})

            # Build volume mounts.
            yield _sse("step", {"message": "Starting container..."})
            volumes: dict[str, str] = {}
            resolved_workspace = str(Path(workspace).resolve())
            ws_mount = f"{CONTAINER_WORKSPACE}:ro" if template.read_only_workspace else CONTAINER_WORKSPACE
            volumes[resolved_workspace] = ws_mount
            if agent.auth_dir:
                resolved_auth = str(Path(agent.auth_dir).expanduser().resolve())
                auth_dirname = Path(agent.auth_dir).name
                volumes[resolved_auth] = f"{CONTAINER_HOME}/{auth_dirname}"

            labels = {
                LABEL_AGENT: agent.agent_type,
                LABEL_TEMPLATE: template.name,
                LABEL_WORKSPACE: resolved_workspace,
            }

            import containerkit
            from ...core.docker import _runtime as _current_runtime
            if _current_runtime is None:
                import sandboxer.core.docker as _docker_mod
                _docker_mod._runtime = containerkit.resolve(config.container_backend)

            rt = get_runtime()
            runtime = config.container_runtime
            if runtime == "runsc" and (rt.name != "docker" or not is_gvisor_available()):
                runtime = None

            await asyncio.to_thread(
                docker_create, image,
                name=sandbox_name, volumes=volumes, labels=labels,
                runtime=runtime,
                network=template.network if template.network != "bridge" else None,
                dns=config.dns_server,
            )
            yield _sse("step", {"message": "Container started."})

            # Credential proxy (best-effort).
            if agent.api_key_env_var:
                try:
                    from ...core.proxy_manager import get_proxy_manager
                    pm = get_proxy_manager()
                    pm.start_proxy(sandbox_name, [agent], port=config.credential_proxy_port)
                    yield _sse("step", {"message": "Credential proxy started."})
                except Exception:
                    pass

            # Metadata.
            resolved_ttl = int(ttl) if ttl else config.default_ttl_seconds
            resolved_idle = int(idle_timeout) if idle_timeout else config.default_idle_timeout_seconds
            if resolved_ttl is not None or resolved_idle is not None:
                try:
                    from ...core.metadata import SandboxMetadata, save_metadata
                    now = datetime.now()
                    meta = SandboxMetadata(
                        name=sandbox_name, created_at=now, last_activity=now,
                        ttl_seconds=resolved_ttl, idle_timeout_seconds=resolved_idle,
                    )
                    await asyncio.to_thread(save_metadata, meta)
                except Exception:
                    pass

            yield _sse("done", {"name": sandbox_name, "redirect": f"/sandboxes/{sandbox_name}"})

        except Exception as exc:
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def sandbox_detail_page(request: Request) -> HTMLResponse:
    """Sandbox detail view."""
    name = request.path_params["name"]
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    sandbox = next((s for s in sandboxes if s.name == name), None)
    if sandbox is None:
        return HTMLResponse("Sandbox not found", status_code=404)
    return request.app.state.templates.TemplateResponse(
        request,
        "sandboxes/detail.html",
        {"sandbox": sandbox},
    )


# ---------------------------------------------------------------------------
# HTMX partials / actions
# ---------------------------------------------------------------------------


async def sandbox_list_partial(request: Request) -> HTMLResponse:
    """Return the sandbox card grid as an HTMX partial."""
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_stats_partial(request: Request) -> HTMLResponse:
    """Return sandbox stats as an HTMX partial."""
    name = request.path_params["name"]
    try:
        stats = await asyncio.to_thread(get_sandbox_stats, name)
    except Exception:
        return HTMLResponse(
            '<div class="text-sm text-slate-500">Stats unavailable</div>'
        )
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/sandbox_stats.html",
        {"stats": stats},
    )


async def sandbox_stop(request: Request) -> HTMLResponse:
    """Stop a sandbox and return the updated list."""
    name = request.path_params["name"]
    await asyncio.to_thread(stop_sandbox, name)
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_remove(request: Request) -> HTMLResponse:
    """Remove a sandbox and return the updated list."""
    name = request.path_params["name"]
    await asyncio.to_thread(remove_sandbox, name)
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_snapshot(request: Request) -> Response:
    """Snapshot a sandbox."""
    name = request.path_params["name"]
    tag = f"{name}:snapshot"
    try:
        await asyncio.to_thread(snapshot_sandbox, name, tag)
    except Exception as exc:
        response = Response(status_code=422)
        response.headers["HX-Trigger"] = (
            '{"showToast": {"message": "Snapshot failed: '
            + str(exc).replace('"', '\\"')
            + '", "level": "error"}}'
        )
        return response
    response = Response(status_code=204)
    response.headers["HX-Trigger"] = (
        '{"showToast": {"message": "Snapshot created: ' + tag + '", "level": "success"}}'
    )
    return response


routes = [
    Route("/sandboxes/", sandbox_list_page),
    Route("/sandboxes/new", sandbox_create_page),
    Route("/sandboxes/", sandbox_create, methods=["POST"]),
    Route("/sandboxes/create/stream", sandbox_create_stream_page),
    Route("/sandboxes/create/events", sandbox_create_events),
    Route("/sandboxes/{name}", sandbox_detail_page),
    Route("/sandboxes/{name}/stats", sandbox_stats_partial),
    Route("/sandboxes/{name}/stop", sandbox_stop, methods=["POST"]),
    Route("/sandboxes/{name}/rm", sandbox_remove, methods=["DELETE"]),
    Route("/sandboxes/{name}/snapshot", sandbox_snapshot, methods=["POST"]),
    Route("/api/sandboxes", sandbox_list_partial),
]
