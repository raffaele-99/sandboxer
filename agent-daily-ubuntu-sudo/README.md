# Ubuntu Daily Agent Container (Autonomous + sudo)

This variant is for fully autonomous runs where the agent can install missing tools during execution.

## What this enables
- Passwordless `sudo` for user `agent`.
- Runtime package installs, e.g. `sudo apt-get update && sudo apt-get install -y <tool>`.
- Codex preinstalled in the image.

## Filesystem boundary
- Host file access is still limited to one bind-mounted host path:
  - `WORKSPACE_DIR -> /workspace`
- No host home-directory mount.
- Codex state persists in a Docker-managed volume at `/home/agent/.codex`.

## Build

From repo root:

```bash
export HOST_UID="$(id -u)"
export HOST_GID="$(id -g)"
export WORKSPACE_DIR="$(pwd)"
docker compose -f docker/agent-daily-ubuntu-sudo/docker-compose.yml build
```

## Open shell

```bash
docker compose -f docker/agent-daily-ubuntu-sudo/docker-compose.yml run --rm codex-agent-daily-sudo
```

Inside:

```bash
whoami
sudo -n true && echo "sudo ok"
codex --version
```

## Unattended run (`--yolo`)

```bash
export OPENAI_API_KEY="..."
docker compose -f docker/agent-daily-ubuntu-sudo/docker-compose.yml run --rm codex-agent-daily-sudo \
  codex --yolo
```

## Example: install missing tool in-container

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

## Important risk note
- This profile is intentionally less hardened than `docker/agent-daily-ubuntu/` so `sudo` works.
- Keep `WORKSPACE_DIR` pointed at a narrow directory, and avoid mounting sensitive host paths.
