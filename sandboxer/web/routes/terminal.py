"""Terminal page + WebSocket handler for interactive shell sessions."""
from __future__ import annotations

import asyncio
import json
import uuid

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect


async def terminal_page(request: Request) -> HTMLResponse:
    """Render the full-screen terminal page."""
    name = request.path_params["name"]
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "terminal.html",
        {"sandbox_name": name},
    )


async def terminal_websocket(websocket: WebSocket) -> None:
    """Bridge a WebSocket to a PTY-backed docker exec session."""
    name = websocket.path_params["name"]
    session_mgr = websocket.app.state.session_manager

    await websocket.accept()

    session_id = f"{name}-{uuid.uuid4().hex[:8]}"
    try:
        session = session_mgr.create(session_id, name)
    except Exception as exc:
        await websocket.send_text(f"\r\nError starting session: {exc}\r\n")
        await websocket.close()
        return

    async def pty_to_ws() -> None:
        """Forward PTY output to the WebSocket."""
        try:
            while session.alive:
                try:
                    data = await asyncio.wait_for(session.read(), timeout=0.5)
                    if data:
                        await websocket.send_bytes(data)
                except asyncio.TimeoutError:
                    continue
                except OSError:
                    break
        except Exception:
            pass

    async def ws_to_pty() -> None:
        """Forward WebSocket input to the PTY."""
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break

                data = message.get("bytes") or (message.get("text", "").encode())
                if not data:
                    continue

                # Check for JSON resize messages.
                try:
                    parsed = json.loads(data)
                    if isinstance(parsed, dict) and parsed.get("type") == "resize":
                        session.resize(parsed["rows"], parsed["cols"])
                        continue
                except (json.JSONDecodeError, ValueError, KeyError):
                    pass

                session.write(data)
        except WebSocketDisconnect:
            pass
        except Exception:
            pass

    try:
        await asyncio.gather(pty_to_ws(), ws_to_pty())
    finally:
        await session_mgr.close(session_id)


routes = [
    Route("/terminal/{name}", terminal_page),
    WebSocketRoute("/ws/terminal/{name}", terminal_websocket),
]
