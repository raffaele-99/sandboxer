# Ubuntu Daily Agent Container

This is a general-purpose Ubuntu container for autonomous Codex runs (`--yolo`) with a tighter filesystem boundary than the dev image.

## What this is for
- Day-to-day computing tasks, not full development toolchains.
- Running Codex with access only to one bind-mounted host directory.

## Security defaults
- Non-root `agent` user.
- No `sudo` in the image.
- Only one host bind mount: `WORKSPACE_DIR -> /workspace`.
- No host home-directory mount.
- Read-only container root filesystem.
- `cap_drop: [ALL]` and `no-new-privileges:true`.

## Build

From repo root:

```bash
export HOST_UID="$(id -u)"
export HOST_GID="$(id -g)"
export WORKSPACE_DIR="$(pwd)"
docker compose -f docker/agent-daily-ubuntu/docker-compose.yml build
```

## Open shell

```bash
docker compose -f docker/agent-daily-ubuntu/docker-compose.yml run --rm codex-agent-daily
```

Inside the container:

```bash
whoami
pwd
ls -la /
codex --version
```

Expected:
- `whoami` is `agent`
- working directory is `/workspace`
- host-visible files are limited to `${WORKSPACE_DIR}`

## Run Codex unattended (`--yolo`)

Set your API key in the host shell if needed:

```bash
export OPENAI_API_KEY="..."
```

Run:

```bash
docker compose -f docker/agent-daily-ubuntu/docker-compose.yml run --rm codex-agent-daily \
  codex --yolo
```

## Notes
- `codex-home` is a Docker-managed volume for `/home/agent/.codex`, so agent state persists without exposing host home files.
- To change the allowed host directory, point `WORKSPACE_DIR` at a different absolute path.
