"""Settings route — view and update GlobalConfig."""
from __future__ import annotations

import asyncio
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

from ...core.config import GlobalConfig


async def settings_page(request: Request) -> HTMLResponse:
    """Render the settings form with current config values."""
    config = await asyncio.to_thread(GlobalConfig.load)
    return request.app.state.templates.TemplateResponse(
        request,
        "settings.html",
        {"config": config},
    )


async def settings_update(request: Request) -> Response:
    """Handle settings form submission."""
    form = await request.form()

    def _int_or_none(key: str) -> int | None:
        val = form.get(key, "").strip()
        return int(val) if val else None

    try:
        config = GlobalConfig(
            default_template=form.get("default_template", "").strip() or None,
            default_agent=form.get("default_agent", "").strip() or None,
            credential_proxy_port=int(form.get("credential_proxy_port", "9876")),
            auto_cleanup_orphans="auto_cleanup_orphans" in form,
            network_mode=form.get("network_mode", "bridge").strip(),
            container_runtime=form.get("container_runtime", "runsc").strip(),
            container_backend=form.get("container_backend", "auto").strip(),
            dns_server=form.get("dns_server", "").strip() or None,
            default_ttl_seconds=_int_or_none("default_ttl_seconds"),
            default_idle_timeout_seconds=_int_or_none("default_idle_timeout_seconds"),
        )
        await asyncio.to_thread(config.save)
    except Exception as exc:
        response = Response(status_code=422)
        response.headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": str(exc), "level": "error"}}
        )
        return response

    response = Response(status_code=204)
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Settings saved.", "level": "success"}}
    )
    return response


routes = [
    Route("/settings", settings_page),
    Route("/settings", settings_update, methods=["PUT"]),
]
