"""Tests for sandboxer.core.models."""
from __future__ import annotations

from datetime import datetime

from sandboxer.core.models import AgentProfile, SandboxInfo, SandboxTemplate


class TestSandboxTemplate:
    def test_defaults(self) -> None:
        tmpl = SandboxTemplate(name="test")
        assert tmpl.name == "test"
        assert tmpl.description == ""
        assert tmpl.base_image == "docker/sandbox-templates:latest"
        assert tmpl.packages == []
        assert tmpl.allow_sudo is False
        assert tmpl.network == "bridge"
        assert tmpl.read_only_workspace is False

    def test_full(self) -> None:
        tmpl = SandboxTemplate(
            name="python-dev",
            description="Python development environment",
            base_image="docker/sandbox-templates:claude-code",
            packages=["vim", "htop"],
            pip_packages=["pytest"],
            npm_packages=["prettier"],
            custom_dockerfile_lines=["RUN echo hello"],
            allow_sudo=True,
            network="none",
            read_only_workspace=True,
        )
        assert tmpl.packages == ["vim", "htop"]
        assert tmpl.pip_packages == ["pytest"]
        assert tmpl.allow_sudo is True


class TestAgentProfile:
    def test_defaults(self) -> None:
        agent = AgentProfile(name="test", agent_type="claude")
        assert agent.api_key_env_var == ""
        assert agent.auth_dir is None
        assert agent.default_args == []

    def test_full(self) -> None:
        agent = AgentProfile(
            name="work",
            agent_type="codex",
            api_key_env_var="OPENAI_API_KEY",
            auth_dir="/home/user/.codex",
            default_args=["--full-auto"],
        )
        assert agent.agent_type == "codex"
        assert agent.default_args == ["--full-auto"]


class TestSandboxInfo:
    def test_defaults(self) -> None:
        info = SandboxInfo(name="test-sandbox")
        assert info.status == "unknown"
        assert info.created_at is None

    def test_serialization(self) -> None:
        now = datetime.now()
        info = SandboxInfo(
            name="sandboxer-py-claude-20260315",
            template="python-dev",
            agent="claude-work",
            workspace="/home/user/project",
            status="running",
            created_at=now,
        )
        data = info.model_dump()
        assert data["name"] == "sandboxer-py-claude-20260315"
        assert data["status"] == "running"
