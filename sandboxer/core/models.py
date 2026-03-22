"""Core data models backed by pydantic."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]*$")


class SandboxTemplate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not _SAFE_NAME_RE.match(v):
            raise ValueError(
                "Template name must contain only alphanumeric characters, "
                "hyphens, and underscores, and must start with an alphanumeric character."
            )
        return v
    description: str = ""
    base_image: str = "docker/sandbox-templates:latest"
    packages: list[str] = Field(default_factory=list)
    pip_packages: list[str] = Field(default_factory=list)
    npm_packages: list[str] = Field(default_factory=list)
    custom_dockerfile_lines: list[str] = Field(default_factory=list)
    allow_sudo: bool = False
    pip_use_venv: bool = True
    pip_venv_path: str = ""
    network: str = "bridge"
    read_only_workspace: bool = False
    agent_type: str | None = None
    registry_source: str | None = None


class AgentProfile(BaseModel):
    name: str
    agent_type: str  # "claude" | "codex" | "gemini"
    api_key_env_var: str = ""  # env var name; actual key stored via keyring
    auth_dir: str | None = None  # host path to mount (e.g. ~/.claude)
    default_args: list[str] = Field(default_factory=list)


class SandboxStats(BaseModel):
    """Resource usage snapshot from ``docker stats``."""

    name: str
    cpu_percent: str = ""
    mem_usage: str = ""
    mem_percent: str = ""
    net_io: str = ""
    block_io: str = ""
    pids: str = ""


class SandboxInfo(BaseModel):
    name: str
    template: str = ""
    agent: str = ""
    workspace: str = ""
    status: str = "unknown"  # "running" | "stopped" | "exited" | "unknown"
    created_at: datetime | None = None
    credential_proxy_url: str | None = None
