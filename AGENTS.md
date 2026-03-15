# Repository Guidelines

## Project Structure & Module Organization
This repository provides `agent-shell`, a Python CLI that dynamically generates Dockerfiles, builds local images, and launches sandboxed containers for autonomous agents (Codex or Claude).

- `agent_shell/cli.py`: main CLI implementation (Typer app, agent adapters, Dockerfile generation, config management).
- `agent_shell/__init__.py`: package version.
- `pyproject.toml`: build metadata, dependencies, and console script entry point.
- `README.md`: user-facing documentation.

## Build, Test, and Development Commands

Install for development:
```bash
pip install -e .
# or
uv tool install --from . agent-shell
```

Run without installing:
```bash
uv run agent-shell codex -m .
```

Smoke-test a container:
```bash
agent-shell codex -o ubuntu:24.04 -m . --dry-run
agent-shell codex -o ubuntu:24.04 -m .
agent-shell claude -o ubuntu:24.04 -m . --allow-sudo
```

Quick validation inside a container:
- `whoami` (expect `agent`)
- `pwd` (expect `/workspace`)
- For sudo containers: `sudo -n true`

## Coding Style & Naming Conventions
- Python: 4-space indentation, type hints, dataclass-based adapters.
- Use Typer for CLI argument definitions with `Annotated` type hints.
- Keep generated Dockerfile package lists alphabetized where practical.

## Testing Guidelines
There is no automated test suite yet. Validate changes with container smoke tests:
1. Run `--dry-run` to inspect the generated Dockerfile.
2. Launch a container and verify user, working directory, and agent availability.
3. For `--allow-sudo`, verify `sudo -n true`.

Document manual test results in PR descriptions.

## Commit & Pull Request Guidelines
- Use short, imperative commit subjects (example: `feat: add Alpine support`).
- Keep commits focused to one logical change.
- PRs should include:
  - purpose and scope,
  - commands run for verification,
  - security-impact notes (mounts, privileges, capabilities),
  - linked issue (if applicable).

## Security & Configuration Tips
- Mount only the minimal workspace directory needed.
- Auth directories (`~/.codex`, `~/.claude`) are mounted read-only by default.
- Prefer running without `--allow-sudo` unless runtime package installation is required.
- All containers run with `cap_drop=ALL`, `no-new-privileges`, and `--network=none` by default.
