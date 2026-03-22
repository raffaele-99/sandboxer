"""Agent profile CRUD routes."""
from __future__ import annotations

import asyncio
import json

from starlette.requests import Request
from starlette.responses import HTMLResponse, Response
from starlette.routing import Route

from ...core.agents import delete_agent, list_agents, load_agent, rename_agent, save_agent
from ...core.models import AgentProfile


async def agent_list_page(request: Request) -> HTMLResponse:
    """Full-page agent list."""
    agents = await asyncio.to_thread(list_agents)
    return request.app.state.templates.TemplateResponse(
        request,
        "agents/list.html",
        {"agents": agents},
    )


async def agent_create_page(request: Request) -> HTMLResponse:
    """Agent creation form."""
    return request.app.state.templates.TemplateResponse(
        request,
        "agents/create.html",
        {"error": None},
    )


async def agent_create(request: Request) -> Response:
    """Handle agent creation form submission."""
    form = await request.form()
    name = form.get("name", "").strip()
    agent_type = form.get("agent_type", "").strip()

    if not name or not agent_type:
        return request.app.state.templates.TemplateResponse(
            request,
            "agents/create.html",
            {"error": "Name and agent type are required."},
        )

    profile = AgentProfile(
        name=name,
        agent_type=agent_type,
        api_key_env_var=form.get("api_key_env_var", "").strip(),
        auth_dir=form.get("auth_dir", "").strip() or None,
    )

    try:
        await asyncio.to_thread(save_agent, profile)
    except Exception as exc:
        return request.app.state.templates.TemplateResponse(
            request,
            "agents/create.html",
            {"error": str(exc)},
        )

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/agents/{name}"
    return response


async def agent_detail_page(request: Request) -> HTMLResponse:
    """Agent detail view."""
    name = request.path_params["name"]
    try:
        agent = await asyncio.to_thread(load_agent, name)
    except FileNotFoundError:
        return HTMLResponse("Agent not found", status_code=404)
    return request.app.state.templates.TemplateResponse(
        request,
        "agents/detail.html",
        {"agent": agent},
    )


async def agent_edit_page(request: Request) -> HTMLResponse:
    """Agent edit form."""
    name = request.path_params["name"]
    try:
        agent = await asyncio.to_thread(load_agent, name)
    except FileNotFoundError:
        return HTMLResponse("Agent not found", status_code=404)
    return request.app.state.templates.TemplateResponse(
        request,
        "agents/edit.html",
        {"agent": agent, "error": None},
    )


async def agent_update(request: Request) -> Response:
    """Handle agent edit form submission."""
    old_name = request.path_params["name"]
    form = await request.form()
    new_name = form.get("name", old_name).strip()
    agent_type = form.get("agent_type", "").strip()

    if not agent_type:
        response = Response(status_code=422)
        response.headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": "Agent type is required.", "level": "error"}}
        )
        return response

    profile = AgentProfile(
        name=new_name,
        agent_type=agent_type,
        api_key_env_var=form.get("api_key_env_var", "").strip(),
        auth_dir=form.get("auth_dir", "").strip() or None,
    )

    try:
        if new_name != old_name:
            await asyncio.to_thread(rename_agent, old_name, new_name)
        await asyncio.to_thread(save_agent, profile)
    except Exception as exc:
        response = Response(status_code=422)
        response.headers["HX-Trigger"] = json.dumps(
            {"showToast": {"message": str(exc), "level": "error"}}
        )
        return response

    response = Response(status_code=204)
    response.headers["HX-Redirect"] = f"/agents/{new_name}"
    response.headers["HX-Trigger"] = json.dumps(
        {"showToast": {"message": "Agent updated.", "level": "success"}}
    )
    return response


async def agent_delete(request: Request) -> Response:
    """Delete an agent profile."""
    name = request.path_params["name"]
    try:
        await asyncio.to_thread(delete_agent, name)
    except Exception as exc:
        response = Response(status_code=422)
        response.headers["HX-Trigger"] = (
            '{"showToast": {"message": "Delete failed: '
            + str(exc).replace('"', '\\"')
            + '", "level": "error"}}'
        )
        return response
    response = Response(status_code=204)
    response.headers["HX-Redirect"] = "/agents/"
    return response


async def agent_list_partial(request: Request) -> HTMLResponse:
    """HTMX partial — agent card grid."""
    agents = await asyncio.to_thread(list_agents)
    return request.app.state.templates.TemplateResponse(
        request,
        "partials/agent_list.html",
        {"agents": agents},
    )


routes = [
    Route("/agents/", agent_list_page),
    Route("/agents/new", agent_create_page),
    Route("/agents/", agent_create, methods=["POST"]),
    Route("/agents/{name}", agent_detail_page),
    Route("/agents/{name}", agent_update, methods=["PUT"]),
    Route("/agents/{name}", agent_delete, methods=["DELETE"]),
    Route("/agents/{name}/edit", agent_edit_page),
    Route("/api/agents", agent_list_partial),
]
