"""Chat interface — structured JSON bridge to agent CLIs."""
from __future__ import annotations

import asyncio
import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from ...core.adapters import get_adapter
from ...core.config import config_dir
from ...core.docker import CONTAINER_HOME, CONTAINER_WORKSPACE, get_runtime
from ...core.sandboxes import list_running_sandboxes


# ---------------------------------------------------------------------------
# Chat session persistence — multiple sessions per sandbox
# ---------------------------------------------------------------------------

def _sessions_dir(sandbox_name: str) -> Path:
    d = config_dir() / "chat_sessions" / sandbox_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def _session_path(sandbox_name: str, session_id: str) -> Path:
    return _sessions_dir(sandbox_name) / f"{session_id}.json"


def _load_session(sandbox_name: str, session_id: str) -> dict:
    """Load a chat session: {id, agent_session_id, title, created_at, messages}."""
    path = _session_path(sandbox_name, session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return {
        "id": session_id,
        "agent_session_id": None,
        "title": "",
        "created_at": time.time(),
        "messages": [],
    }


def _save_session(sandbox_name: str, state: dict) -> None:
    _session_path(sandbox_name, state["id"]).write_text(json.dumps(state, indent=2))


def _append_message(sandbox_name: str, role: str, text: str, state: dict) -> None:
    state["messages"].append({"role": role, "text": text, "ts": time.time()})
    # Auto-title from first user message.
    if not state.get("title") and role == "user":
        state["title"] = text[:80]
    _save_session(sandbox_name, state)


def _list_sessions(sandbox_name: str) -> list[dict]:
    """List all sessions for a sandbox, newest first."""
    d = _sessions_dir(sandbox_name)
    sessions = []
    for f in d.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            sessions.append({
                "id": data.get("id", f.stem),
                "title": data.get("title", "Untitled"),
                "created_at": data.get("created_at", 0),
                "message_count": len(data.get("messages", [])),
            })
        except Exception:
            continue
    sessions.sort(key=lambda s: s["created_at"], reverse=True)
    return sessions


def _delete_session(sandbox_name: str, session_id: str) -> None:
    path = _session_path(sandbox_name, session_id)
    path.unlink(missing_ok=True)


def _migrate_old_session(sandbox_name: str) -> None:
    """Migrate old single-file session format to new multi-session format."""
    old_path = config_dir() / "chat_sessions" / f"{sandbox_name}.json"
    if not old_path.exists():
        return
    try:
        old_data = json.loads(old_path.read_text())
        if "messages" in old_data and old_data["messages"]:
            session_id = str(uuid.uuid4())[:8]
            new_state = {
                "id": session_id,
                "agent_session_id": old_data.get("session_id"),
                "title": "",
                "created_at": old_data["messages"][0].get("ts", time.time()),
                "messages": old_data["messages"],
            }
            # Title from first user message.
            for m in old_data["messages"]:
                if m.get("role") == "user":
                    new_state["title"] = m["text"][:80]
                    break
            _save_session(sandbox_name, new_state)
        old_path.unlink()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Agent command builders
# ---------------------------------------------------------------------------

def _build_agent_cmd(
    sandbox_name: str,
    agent_type: str,
    cli_binary: str,
    prompt: str,
    *,
    agent_session_id: str | None = None,
    env: dict[str, str] | None = None,
) -> list[str]:
    """Build the container exec command for an agent invocation."""
    rt = get_runtime()

    if agent_type == "claude":
        agent_cmd = [
            cli_binary,
            "-p",
            "--dangerously-skip-permissions",
            "--output-format", "stream-json",
            "--verbose",
        ]
        if agent_session_id:
            agent_cmd.extend(["--resume", agent_session_id])
        agent_cmd.append(prompt)
    elif agent_type == "codex":
        if agent_session_id:
            agent_cmd = [
                cli_binary,
                "exec", "resume", agent_session_id,
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                prompt,
            ]
        else:
            agent_cmd = [
                cli_binary,
                "exec",
                "--json",
                "--dangerously-bypass-approvals-and-sandbox",
                prompt,
            ]
    elif agent_type == "gemini":
        agent_cmd = [cli_binary, "-p", prompt]
    else:
        agent_cmd = [cli_binary, prompt]

    return rt.build_exec_command(
        sandbox_name, agent_cmd, workdir=CONTAINER_WORKSPACE, env=env,
    )


def _extract_session_id(agent_type: str, line_data: dict) -> str | None:
    """Try to extract a session/thread ID from a parsed JSON event."""
    if agent_type == "codex" and line_data.get("type") == "thread.started":
        return line_data.get("thread_id")
    if agent_type == "claude" and line_data.get("type") == "system":
        return line_data.get("session_id")
    return None


# ---------------------------------------------------------------------------
# Background agent tasks — survive WebSocket disconnects
# ---------------------------------------------------------------------------

@dataclass
class AgentTask:
    """A running agent process with buffered output."""

    sandbox_name: str
    session_id: str
    agent_type: str
    proc: subprocess.Popen | None = None
    status: str = "running"  # running | done | error
    events: list[dict] = field(default_factory=list)
    assistant_text_parts: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    subscribers: set[WebSocket] = field(default_factory=set)
    _task: asyncio.Task | None = field(default=None, repr=False)


# Key: (sandbox_name, session_id) → AgentTask
_active_tasks: dict[tuple[str, str], AgentTask] = {}

# Dedicated thread pool for agent I/O so concurrent agents don't starve
# the default executor (used by the rest of the app).
import concurrent.futures as _cf
_agent_executor = _cf.ThreadPoolExecutor(max_workers=32, thread_name_prefix="agent-io")


def _get_task(sandbox_name: str, session_id: str) -> AgentTask | None:
    return _active_tasks.get((sandbox_name, session_id))


async def _broadcast(task: AgentTask, event: dict) -> None:
    """Send an event to all connected subscribers and buffer it."""
    task.events.append(event)
    dead: set[WebSocket] = set()
    for ws in task.subscribers:
        try:
            await ws.send_text(json.dumps(event))
        except Exception:
            dead.add(ws)
    task.subscribers -= dead


async def _run_agent_task(
    task: AgentTask,
    cmd: list[str],
    adapter_agent_type: str,
    chat_state: dict,
) -> None:
    """Run the agent CLI in the background, buffering all events."""
    sandbox_name = task.sandbox_name
    _HEARTBEAT_INTERVAL = 3

    try:
        proc = await asyncio.to_thread(
            lambda: subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        )
        task.proc = proc

        loop = asyncio.get_running_loop()
        got_output = False
        json_buffer = ""

        while True:
            # Read a line with heartbeat.
            line: str | None = None
            while True:
                read_fut = loop.run_in_executor(
                    _agent_executor, proc.stdout.readline,  # type: ignore[union-attr]
                )
                try:
                    line = await asyncio.wait_for(
                        asyncio.shield(read_fut), timeout=_HEARTBEAT_INTERVAL,
                    )
                    break
                except asyncio.TimeoutError:
                    rc = proc.poll()
                    elapsed = int(time.time() - task.started_at)
                    if rc is not None:
                        await read_fut
                        line = None
                        break
                    await _broadcast(task, {
                        "type": "status",
                        "status": "processing",
                        "elapsed": elapsed,
                    })
                    try:
                        line = await asyncio.wait_for(
                            read_fut, timeout=_HEARTBEAT_INTERVAL,
                        )
                        break
                    except asyncio.TimeoutError:
                        continue

            if not line:
                break
            got_output = True
            stripped = line.strip()
            if not stripped:
                continue

            # JSON parsing with multi-line buffer.
            if not json_buffer:
                try:
                    parsed = json.loads(stripped)
                except json.JSONDecodeError:
                    json_buffer = stripped
                    continue
            else:
                json_buffer += "\n" + stripped
                try:
                    parsed = json.loads(json_buffer)
                    json_buffer = ""
                except json.JSONDecodeError:
                    if len(json_buffer) > 1_000_000:
                        json_buffer = ""
                    continue

            # Extract agent session ID.
            sid = _extract_session_id(adapter_agent_type, parsed)
            if sid and not chat_state.get("agent_session_id"):
                chat_state["agent_session_id"] = sid
                await asyncio.to_thread(_save_session, sandbox_name, chat_state)
                await _broadcast(task, {
                    "type": "agent_session.id",
                    "agent_session_id": sid,
                })

            # Collect assistant text for history.
            if adapter_agent_type == "codex":
                if parsed.get("type") == "item.completed":
                    item = parsed.get("item", {})
                    if item.get("type") == "agent_message" and item.get("text"):
                        task.assistant_text_parts.append(item["text"])
                    elif item.get("type") == "command_execution":
                        cmd_str = item.get("command", "command")
                        output = item.get("aggregated_output", "")
                        if output:
                            task.assistant_text_parts.append(
                                f"```\n$ {cmd_str}\n{output}\n```"
                            )
                    elif item.get("type") in (
                        "file_edit", "file_create", "file_write",
                    ):
                        fp = (
                            item.get("filepath")
                            or item.get("path")
                            or item.get("filename")
                            or "file"
                        )
                        content = item.get("content") or item.get("text") or ""
                        if content:
                            task.assistant_text_parts.append(
                                f"Wrote `{fp}`:\n```\n{content[:2000]}\n```"
                            )
            elif adapter_agent_type == "claude":
                if parsed.get("type") == "assistant":
                    content = (parsed.get("message") or {}).get("content", [])
                    for block in content:
                        if block.get("type") == "text" and block.get("text"):
                            task.assistant_text_parts.append(block["text"])
                elif parsed.get("type") == "content_block_delta":
                    delta_text = (parsed.get("delta") or {}).get("text", "")
                    if delta_text:
                        task.assistant_text_parts.append(delta_text)
                elif (
                    parsed.get("type") == "result"
                    and parsed.get("result")
                    and not parsed.get("is_error")
                ):
                    if not task.assistant_text_parts:
                        task.assistant_text_parts.append(parsed["result"])

            await _broadcast(task, parsed)

        await asyncio.to_thread(proc.wait)

        stderr = await asyncio.to_thread(
            lambda: proc.stderr.read()  # type: ignore[union-attr]
        )
        if proc.returncode != 0:
            err_msg = (stderr or "").strip()
            if not err_msg and not got_output:
                err_msg = f"Agent process exited with code {proc.returncode}"
            if err_msg:
                await _broadcast(task, {
                    "type": "result",
                    "is_error": True,
                    "result": err_msg,
                })

        task.status = "done"

    except Exception as exc:
        task.status = "error"
        await _broadcast(task, {
            "type": "result",
            "is_error": True,
            "result": f"Error: {exc}",
        })

    finally:
        # Save assistant response.
        if task.assistant_text_parts:
            full_text = "\n\n".join(task.assistant_text_parts)
            await asyncio.to_thread(
                _append_message, sandbox_name, "assistant", full_text, chat_state,
            )
            task.assistant_text_parts.clear()
        # Clean up.
        if task.proc is not None and task.proc.poll() is None:
            task.proc.kill()
        _active_tasks.pop((sandbox_name, task.session_id), None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

async def chat_page(request: Request) -> HTMLResponse:
    """Render the chat UI page."""
    name = request.path_params["name"]
    session_id = request.query_params.get("session", "")
    token = (
        request.cookies.get("sandboxer_token", "")
        or request.query_params.get("token", "")
    )

    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    sandbox = next((s for s in sandboxes if s.name == name), None)
    agent_type = sandbox.agent if sandbox else ""

    # Migrate old format if needed.
    await asyncio.to_thread(_migrate_old_session, name)

    return request.app.state.templates.TemplateResponse(
        request,
        "chat.html",
        {
            "sandbox_name": name,
            "ws_token": token,
            "agent_type": agent_type,
            "session_id": session_id,
        },
    )


async def chat_sessions_list(request: Request) -> JSONResponse:
    """Return list of chat sessions for a sandbox."""
    name = request.path_params["name"]
    await asyncio.to_thread(_migrate_old_session, name)
    sessions = await asyncio.to_thread(_list_sessions, name)
    return JSONResponse(sessions)


async def chat_session_create(request: Request) -> JSONResponse:
    """Create a new chat session. Returns {id}."""
    name = request.path_params["name"]
    session_id = str(uuid.uuid4())[:8]
    state = {
        "id": session_id,
        "agent_session_id": None,
        "title": "",
        "created_at": time.time(),
        "messages": [],
    }
    await asyncio.to_thread(_save_session, name, state)
    return JSONResponse({"id": session_id})


async def chat_session_delete(request: Request) -> Response:
    """Delete a chat session."""
    name = request.path_params["name"]
    session_id = request.path_params["session_id"]
    await asyncio.to_thread(_delete_session, name, session_id)
    return Response(status_code=204)


async def chat_history(request: Request) -> JSONResponse:
    """Return the stored chat history for a specific session."""
    name = request.path_params["name"]
    session_id = request.query_params.get("session", "")
    if not session_id:
        return JSONResponse({"messages": []})
    state = await asyncio.to_thread(_load_session, name, session_id)
    # Include whether an agent task is currently running.
    task = _get_task(name, session_id)
    state["agent_running"] = task is not None and task.status == "running"
    return JSONResponse(state)


async def chat_websocket(websocket: WebSocket) -> None:
    """Bridge chat messages to/from the agent CLI via structured JSON."""
    name = websocket.path_params["name"]
    session_id = websocket.query_params.get("session", "")

    # Look up agent type.
    sandboxes = await asyncio.to_thread(list_running_sandboxes)
    sandbox = next((s for s in sandboxes if s.name == name), None)
    if not sandbox or not sandbox.agent:
        await websocket.accept()
        await websocket.send_text(
            json.dumps({"type": "result", "is_error": True, "result": "No agent configured for this sandbox"})
        )
        await websocket.close()
        return

    adapter = get_adapter(sandbox.agent)
    if not adapter or not adapter.cli_binary:
        await websocket.accept()
        await websocket.send_text(
            json.dumps({"type": "result", "is_error": True, "result": f"Unknown agent type: {sandbox.agent}"})
        )
        await websocket.close()
        return

    await websocket.accept()

    # Create session if needed.
    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        await websocket.send_text(json.dumps({"type": "session.created", "session_id": session_id}))

    chat_state = await asyncio.to_thread(_load_session, name, session_id)

    # Send existing agent session ID if resuming.
    if chat_state.get("agent_session_id"):
        await websocket.send_text(json.dumps({
            "type": "agent_session.id",
            "agent_session_id": chat_state["agent_session_id"],
        }))

    # Check if there's an active background task for this session.
    # If so, replay buffered events and subscribe.
    existing_task = _get_task(name, session_id)
    if existing_task and existing_task.status == "running":
        # Replay buffered events from the current turn.
        for event in existing_task.events:
            try:
                await websocket.send_text(json.dumps(event))
            except Exception:
                return
        # Subscribe to future events.
        existing_task.subscribers.add(websocket)
        await websocket.send_text(json.dumps({
            "type": "status",
            "status": "processing",
            "reconnected": True,
            "elapsed": int(time.time() - existing_task.started_at),
        }))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "user" or not msg.get("message"):
                continue

            user_text = msg["message"]
            await asyncio.to_thread(_append_message, name, "user", user_text, chat_state)

            # Ensure agent CLI finds auth/config mounted at CONTAINER_HOME.
            exec_env: dict[str, str] = {"HOME": CONTAINER_HOME}
            try:
                from ...core.sandboxes import _proxy_env

                exec_env.update(_proxy_env(name))
            except Exception:
                pass

            cmd = _build_agent_cmd(
                name, adapter.agent_type, adapter.cli_binary, user_text,
                agent_session_id=chat_state.get("agent_session_id"),
                env=exec_env,
            )

            # Create a background task for this agent invocation.
            task = AgentTask(
                sandbox_name=name,
                session_id=session_id,
                agent_type=adapter.agent_type,
                subscribers={websocket},
            )
            _active_tasks[(name, session_id)] = task
            task._task = asyncio.create_task(
                _run_agent_task(task, cmd, adapter.agent_type, chat_state)
            )

            # Wait for the task to finish OR the websocket to disconnect.
            # If the websocket disconnects, the task keeps running in the
            # background — the user can reconnect and see buffered output.
            try:
                while task.status == "running":
                    # Keep reading from websocket to detect disconnects.
                    # We use a short timeout so we can check task status.
                    try:
                        ws_msg = await asyncio.wait_for(
                            websocket.receive_text(), timeout=1.0,
                        )
                        # Could handle cancel/interrupt here in the future.
                    except asyncio.TimeoutError:
                        continue
            except WebSocketDisconnect:
                # Unsubscribe but let the task keep running.
                task.subscribers.discard(websocket)
                return

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # Unsubscribe from any active task.
        task = _get_task(name, session_id)
        if task:
            task.subscribers.discard(websocket)


routes = [
    Route("/chat/{name}", chat_page),
    Route("/chat/{name}/sessions", chat_sessions_list),
    Route("/chat/{name}/sessions", chat_session_create, methods=["POST"]),
    Route("/chat/{name}/sessions/{session_id}", chat_session_delete, methods=["DELETE"]),
    Route("/chat/{name}/history", chat_history),
    WebSocketRoute("/ws/chat/{name}", chat_websocket),
]
