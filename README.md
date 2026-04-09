# sandboxer

### What

`sandboxer` makes it faster to create one-off containers for autonomous terminal agents.

Right now, it supports:

- Reusable templates
- Per-agent profiles (`claude`, `qwen`, `codex`, etc)
- Credential proxying
- Auto-cleanup of unused containers

### Why

I primarily use terminal agents as a faster way of extending scripts that I've written. While I definitely found their results to be better/more in-depth, I noticed that I was actually taking longer than before to produce the same work; this is apparently a [documented thing](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/). In my case, I wasn't specifically tracking why I was taking longer, but I'm assuming it's because the agents have to keep asking for approval to perform each task.

> *"Can I view the contents of this directory?"* *"Can I check what packages you have installed?"* Yes dude, do whatever you need to finish the Python script. You can put music on if you want, I don't care. Tool call web search for pictures of Owen Wilson, put his face on The Death Of Julius Caesar, go nuts. You're only modifying the contents of this one Python script, so I don't care what web requests you make or what temporary directories you create.

I started using [docker sandbox](https://docs.docker.com/ai/sandboxes/) to give agents their own "host" where they have full permissions - modify files, sudo privileges for tool installs, perform web searches, etc - and I have found that this works much better. I create the sandbox, give the agent my starting script, and ask it to work until all the desired functions are achieved. Then I continue my own work in the meantime and come back 10-20 minutes later to a (usually) fleshed-out script.

**Control.** This project actually started as a wrapper around `docker sandbox`, but I kept hitting walls. The CLI has a rigid, opinionated interface — no `--network` flag, no env var passthrough, no control over volume mounts. That last one was the dealbreaker: I needed to mount agent auth directories (like `~/.codex`) into containers, control which host paths are exposed, and optionally mount workspaces as read-only. `docker sandbox` just doesn't bend that way. So I replaced it with plain `docker run` (with optional gVisor isolation), and later abstracted the runtime entirely via [pycontainer](https://github.com/raffaele-99/pycontainer) to support Apple Containers too.

**Credential isolation.** `docker sandbox` doesn't have an opinion about how your agent authenticates — your API key typically ends up as an env var inside the container, where any code the agent runs can read it. `sandboxer` runs a host-side credential proxy that intercepts API calls and injects auth headers on the fly. The key never enters the container.

**Templates and reproducibility.** `docker sandbox` gives you a one-off environment. If you want "Python 3.12 with pytest, git, and Claude pre-installed" as a thing you can spin up repeatedly, you're back to managing Dockerfiles yourself. `sandboxer` templates capture all of that — OS packages, pip/npm deps, agent type — in a single config you can version, share, and push to a registry.

**Multi-agent, multi-runtime.** If you're comparing Claude, Codex, and Gemini on the same task, `sandboxer` handles the differences for you — different CLI invocations, different streaming formats, different install steps. It also works with Apple Containers on macOS, not just Docker.

**Lifecycle management.** TTL policies, idle timeouts, orphan cleanup, resource monitoring, snapshots — the kind of stuff you end up scripting around `docker sandbox` once you have more than a couple of environments running.

None of this means `docker sandbox` is bad. It's more that `sandboxer` is what you reach for when you're running agents regularly and want guardrails that go beyond "here's a container."

## Usage

### Install

With [`uv`](https://docs.astral.sh/uv/) (recommended):
```bash
git clone https://github.com:raffaele-99/sandboxer.git
cd sandboxer
uv tool install --from . sandboxer
```

To upgrade:
```bash
cd sandboxer
git pull
uv tool upgrade --from . sandboxer
```

With `pipx`:
```bash
pipx install .
```

With a manual venv:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Prerequisites

- A container runtime — either **Docker** or **Apple Containers** (macOS).
  - The runtime is auto-detected; you can override with the `container_backend` config key.
- **Option A — API keys** (recommended): set environment variables for the agents you use. The credential proxy will inject keys into requests so sandboxes never see raw credentials.
  - Claude: `ANTHROPIC_API_KEY`
  - Codex: `OPENAI_API_KEY`
  - Gemini: `GOOGLE_API_KEY`
- **Option B — Auth directory mount**: if you don't have an API key (e.g. you use a Claude Pro/Max subscription via Claude Code), you can mount the agent's auth directory (e.g. `~/.claude`) into the sandbox with `--auth-dir`. See [Auth directory mount](#auth-directory-mount) below.

### Quick start

```bash
# Create a template
sandboxer template create python-dev --base docker/sandbox-templates:latest \
  --package vim --package git --pip pytest --agent-type claude

# Create an agent profile
sandboxer agent create my-claude --type claude

# Launch a sandbox
sandboxer sandbox create python-dev my-claude -w .

# Open a shell
sandboxer sandbox shell sandboxer-python-dev-my-claude-20260315120000

# Check resource usage
sandboxer sandbox stats sandboxer-python-dev-my-claude-20260315120000

# Stop and remove
sandboxer sandbox stop sandboxer-python-dev-my-claude-20260315120000
sandboxer sandbox rm sandboxer-python-dev-my-claude-20260315120000
```

### Commands

#### Sandbox management

| Command | Description |
|---|---|
| `sandbox create <template> <agent>` | Create a sandbox from a template and agent profile |
| `sandbox ls` | List running sandboxer-managed sandboxes |
| `sandbox shell <name>` | Open an interactive shell |
| `sandbox stats <name>` | Show CPU, memory, network, and I/O usage |
| `sandbox snapshot <name> <tag>` | Commit sandbox state as a container image |
| `sandbox stop <name>` | Stop a sandbox |
| `sandbox rm <name>` | Remove a sandbox |

Options for `sandbox create`:
- `-w, --workspace` — host directory to mount (default: `.`)
- `-n, --name` — sandbox name (auto-generated if omitted)
- `--ttl <seconds>` — auto-cleanup after this many seconds
- `--idle-timeout <seconds>` — auto-cleanup after inactivity

Options for `sandbox snapshot`:
- `--register` — also create a local template from the snapshot
- `--as <name>` — override the auto-derived template name

#### Template management

| Command | Description |
|---|---|
| `template create <name>` | Create a new template |
| `template ls` | List templates |
| `template show <name>` | Show template details |
| `template rm <name>` | Delete a template |
| `template push <name> <registry-tag>` | Push a template image to a registry |
| `template pull <registry-tag>` | Pull and register a template from a registry |

Options for `template create`:
- `-b, --base` — base container image (default: `docker/sandbox-templates:latest`)
- `-d, --desc` — description
- `-p, --package` — OS package to install (repeatable)
- `--pip` — pip package to install (repeatable)
- `--npm` — npm package to install (repeatable)
- `-a, --agent-type` — embed agent install in the template (`claude`, `codex`, `gemini`)

Options for `template pull`:
- `--as <name>` — local template name

#### Agent profiles

| Command | Description |
|---|---|
| `agent create <name>` | Create an agent profile |
| `agent ls` | List profiles |
| `agent rm <name>` | Delete a profile |

Options for `agent create`:
- `-t, --type` — agent type: `claude`, `codex`, `gemini` (default: `claude`)
- `-e, --env-var` — API key environment variable (auto-detected from type)
- `--auth-dir` — host auth directory to mount

#### Mount allowlist

| Command | Description |
|---|---|
| `mount ls` | List allowed mount paths |
| `mount add <path>` | Add a path to the allowlist |
| `mount rm <path>` | Remove a path from the allowlist |

#### Cleanup

```bash
sandboxer cleanup              # Remove orphaned, expired, and idle sandboxes
sandboxer cleanup --dry-run    # Preview without removing
sandboxer cleanup --expired    # Only TTL-expired sandboxes
sandboxer cleanup --idle       # Only idle-timeout sandboxes
```

#### Configuration

```bash
sandboxer config               # Show current config
```

Config is stored at `~/.config/sandboxer/config.yml`. Supported keys:

| Key | Default | Description |
|---|---|---|
| `default_template` | `null` | Template to use when none specified |
| `default_agent` | `null` | Agent profile to use when none specified |
| `credential_proxy_port` | `9876` | Starting port for credential proxies |
| `auto_cleanup_orphans` | `true` | Auto-remove stopped sandboxes |
| `network_mode` | `bridge` | Default network mode |
| `container_backend` | `auto` | Container runtime: `auto`, `docker`, or `apple` |
| `container_runtime` | `runsc` | OCI runtime for gVisor isolation (Docker only, falls back gracefully) |
| `default_ttl_seconds` | `null` | Default TTL for new sandboxes |
| `default_idle_timeout_seconds` | `null` | Default idle timeout for new sandboxes |

### Features

- **Multi-runtime** — supports Docker and Apple Containers via [pycontainer](https://github.com/raffaele-99/pycontainer), with automatic detection
- **Templates** — reusable sandbox definitions with OS packages, pip/npm deps, and custom Dockerfile lines
- **Agent adapters** — built-in install snippets for Claude, Codex, and Gemini
- **Credential proxy** — host-side HTTP proxy injects API keys so sandboxes never see real credentials
- **Resource monitoring** — container stats integration for CPU, memory, network, and I/O
- **Snapshots** — commit a running sandbox as a reusable image
- **Template marketplace** — push/pull templates to/from OCI registries
- **Auto-cleanup** — TTL and idle-timeout policies with metadata tracking
- **Mount allowlist** — block sensitive host paths (`.ssh`, `.aws`, `.gnupg`, etc.)
- **gVisor isolation** — optional `runsc` runtime for syscall-level sandboxing (Docker only)

### Auth directory mount

> **Security warning:** Using `--auth-dir` mounts your host auth directory directly into the sandbox container. This **bypasses the credential proxy** — the sandbox will have direct access to your auth tokens and session data. Only use this option if you do not have an API key and understand the security trade-off. The credential proxy (Option A) is the recommended approach because it ensures sandboxed agents never see raw credentials.

To use a subscription-based agent (e.g. Claude Code with a Claude Pro/Max subscription):

```bash
# Create an agent profile with auth dir instead of API key
sandboxer agent create my-claude --type claude --env-var "" --auth-dir ~/.claude

# Launch a sandbox — ~/.claude is mounted into the container
sandboxer sandbox create python-dev my-claude -w .
```

When `--auth-dir` is set and no API key env var is configured, the credential proxy is not started. The agent inside the sandbox authenticates directly using the mounted session data.

### Development

```bash
# Run unit tests (no container runtime needed)
uv run --extra dev python -m pytest tests/ -v -m "not integration"

# Run integration tests (requires Docker or Apple Containers)
uv run --extra dev python -m pytest tests/ -v -m integration
```
