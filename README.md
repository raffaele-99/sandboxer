# Docker Agent Setups

This repo contains Ubuntu-based Docker agent setups for autonomous Codex runs.

## Included
- `agent-daily-ubuntu/`: hardened daily-use profile (no sudo).
- `agent-daily-ubuntu-sudo/`: autonomous profile with passwordless sudo and runtime tool installs.

See each directory's `README.md` for build and run instructions.

## MVP: `agent-shell` (Python + Docker)
This repository includes a Python `agent-shell` command that generates per-run Dockerfiles, builds local images, and launches an interactive container immediately.

### Install
With `uv`:
```bash
uv tool install --from . agent-shell
```

Upgrade after pulling new commits:
```bash
uv tool upgrade --from . agent-shell
```

### Prerequisites
- Docker engine available from your shell (`docker info` must work).
- API key in your shell:
  - Codex: `OPENAI_API_KEY`
  - Claude: `ANTHROPIC_API_KEY`

### Usage
```bash
./agent-shell codex -os ubuntu:24.04 -p ghidra radare2 -m . --allow-sudo
./agent-shell claude -os alpine:3.20 -p gdb strace -m .
./agent-shell -m . -p ripgrep -a codex
./agent-shell --config
```

### What it does
1. Generates a Dockerfile in `~/.cache/agent-shell/dockerfiles/` (or `$XDG_CACHE_HOME/agent-shell/dockerfiles/`) for the selected `--os`.
2. Builds/reuses a local Docker image keyed by agent + OS + package set.
3. Installs requested packages with the image's native package manager.
4. Optionally enables passwordless `sudo` for user `agent`.
5. Mounts agent auth (`~/.codex` or `~/.claude`) directly into `/home/agent`.
6. Sets a colored Bash prompt (`user@host:path`) for interactive shells.
7. Starts `docker run --rm -it` and drops you into `/workspace`.

### Config defaults
Run `./agent-shell --config` to open an interactive setup wizard.  
Config file path: `~/.config/agent-shell/config.yml`

Supported keys:
- `default_agent`: `codex`, `claude`, or `null`
- `default_allow_sudo`: `true` or `false`

### Current support
- Supported agents: `codex`, `claude`.
- `--os` supports these image families:
  - Debian/Ubuntu (`apt`)
  - Alpine (`apk`)
  - Fedora/RHEL family (`dnf`/`yum`)
  - Arch (`pacman`)
  - openSUSE/SLES (`zypper`)
- `-p/--package` values are passed directly to the selected package manager, so package names may differ across OS families.
