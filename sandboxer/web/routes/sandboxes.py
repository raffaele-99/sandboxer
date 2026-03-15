"""HTMX partial endpoints for sandbox CRUD operations."""
from __future__ import annotations

import asyncio

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route

from ...core.sandboxes import (
    list_running_sandboxes,
    remove_sandbox,
    stop_sandbox,
)


async def sandbox_list_partial(request: Request) -> HTMLResponse:
    """Return the sandbox table body as an HTMX partial."""
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_stop(request: Request) -> HTMLResponse:
    """Stop a sandbox and return the updated list."""
    name = request.path_params["name"]
    await asyncio.to_thread(stop_sandbox, name)
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


async def sandbox_remove(request: Request) -> HTMLResponse:
    """Remove a sandbox and return the updated list."""
    name = request.path_params["name"]
    await asyncio.to_thread(remove_sandbox, name)
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "partials/sandbox_list.html",
        {"sandboxes": sandboxes},
    )


routes = [
    Route("/sandboxes", sandbox_list_partial),
    Route("/sandboxes/{name}/stop", sandbox_stop, methods=["POST"]),
    Route("/sandboxes/{name}/rm", sandbox_remove, methods=["DELETE"]),
]
