"""Dashboard route — sandbox overview page."""
from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from ...core.sandboxes import list_running_sandboxes


async def dashboard(request: Request) -> HTMLResponse:
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    templates = request.app.state.templates
    html = templates.TemplateResponse(
        request,
        "dashboard.html",
        {"sandboxes": sandboxes},
    )
    return html


routes = [
    Route("/", dashboard),
]
