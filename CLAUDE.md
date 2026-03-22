# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run tests (unit only, no container runtime needed)
uv run --extra dev python -m pytest tests/ -v --ignore=tests/test_web.py -m "not integration"

# Run integration tests (requires Docker or Apple Containers)
uv run --extra dev python -m pytest tests/ -v -m integration

# Run a single test file
uv run --extra dev python -m pytest tests/test_templates.py -v

# Run the CLI without installing
uv run sandboxer template ls

# Start the web UI
uv run sandboxer serve --host 0.0.0.0 --port 8080

# Install for development
pip install -e ".[dev]"
```

No linter or formatter is configured.

## Architecture

Three-layer design: **CLI** (`cli.py`) → **Core** (`core/`) → **Web** (`web/`).

### Core layer (`sandboxer/core/`)

Stateless functions organized by concern. All state lives in YAML/JSON files under `~/.config/sandboxer/`.

- **models.py** — Pydantic models: `SandboxTemplate`, `AgentProfile`, `SandboxInfo`, `SandboxStats`
- **docker.py** — Container management via [containerkit](https://github.com/raffaele-99/containerkit), a runtime-agnostic abstraction supporting both Docker and Apple Containers. Uses `containerkit.resolve()` for auto-detection, `Runtime.build_exec_command()` / `Runtime.run()` for operations, and `Mount`/`RunOptions` for portable configuration. Labels (`sandboxer.managed`, `sandboxer.agent`, etc.) track containers. Containers run `sleep infinity` as entrypoint; agent CLIs are invoked via exec. The `get_runtime()` function exposes the resolved `containerkit.Runtime` instance.
- **sandboxes.py** — Orchestrates sandbox creation: resolves image from template+agent, builds volume mounts, starts credential proxy, saves metadata. Entry point: `create_sandbox()`.
- **adapters.py** — Maps agent types (claude/codex/gemini) to CLI binaries and Dockerfile install snippets.
- **credential_proxy.py** — Asyncio HTTP proxy that intercepts requests to AI API endpoints and injects auth headers from host env vars. Sandboxes never see raw API keys.
- **config.py** — `GlobalConfig` dataclass, path helpers, blocked mount patterns. `container_runtime` defaults to `"runsc"` (gVisor, Docker only) with automatic fallback. `container_backend` defaults to `"auto"` (auto-detect Docker vs Apple Containers).

### Web layer (`sandboxer/web/`)

Starlette + Jinja2 + HTMX. No SPA framework. Tailwind CSS via CDN (dark theme).

- **app.py** — `create_app()` factory, mounts all route modules, sets up Jinja2 templates and static files.
- **auth.py** — `TokenAuthMiddleware` checks bearer token, cookie, or `?token=` query param. Exempts `/static/*`.
- **terminal.py** — `TerminalSession` opens a real PTY via `containerkit.Runtime.build_exec_command()`, bridged to WebSocket for Xterm.js. Uses a dedicated 16-thread executor for PTY I/O.
- **routes/chat.py** — Multi-session chat. Stores sessions as JSON in `~/.config/sandboxer/chat_sessions/{sandbox}/{session_id}.json`. WebSocket handler spawns agent CLI subprocess per message, streams structured JSON (Claude stream-json or Codex JSONL) back to the browser.

### Route pattern

All web routes follow the same async pattern:
```python
async def handler(request: Request) -> HTMLResponse:
    data = await asyncio.to_thread(core_function)
    return request.app.state.templates.TemplateResponse(request, "template.html", {"data": data})
```

HTMX partials live in `templates/partials/` and are returned from dedicated endpoints for partial DOM updates.

### Agent CLI bridging (chat)

The chat WebSocket bridges messages to agent CLIs running inside containers via `containerkit.Runtime.build_exec_command()`:
- **Claude**: `<runtime> exec <name> claude -p --output-format stream-json --resume <session_id> <prompt>`
- **Codex**: `<runtime> exec <name> codex exec [resume <session_id>] --json --dangerously-bypass-approvals-and-sandbox <prompt>`

Session IDs are extracted from the first response (`system.session_id` for Claude, `thread.started.thread_id` for Codex) and stored for resume.

### Container setup

Containers use containerkit's `Runtime.run()` (which maps to `docker run` or `container run` depending on the detected runtime) with optional `--runtime=runsc` for gVisor syscall isolation (Docker only). Volumes are represented as `containerkit.Mount` objects with automatic syntax translation between runtimes. Default images come from `docker/sandbox-templates:{agent_type}`.

## Testing

Tests in `tests/` use pytest. Integration tests are marked with `@pytest.mark.integration` and require a container runtime (Docker or Apple Containers). Unit tests do not require any container runtime. Web tests are in `test_web.py` (often excluded during development).
