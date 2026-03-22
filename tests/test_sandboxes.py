"""Integration tests for sandboxer.core.sandboxes — requires a container runtime."""
from __future__ import annotations

import pytest

from sandboxer.core.config import GlobalConfig
from sandboxer.core.docker import is_docker_available, remove
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.sandboxes import (
    create_sandbox,
    get_sandbox_stats,
    list_running_sandboxes,
    remove_sandbox,
    snapshot_sandbox,
    stop_sandbox,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_runtime():
    if not is_docker_available():
        pytest.skip("No container runtime available")


class TestCreateSandbox:
    def test_create_with_defaults(self, tmp_path) -> None:
        tmpl = SandboxTemplate(name="python-dev")
        agent = AgentProfile(name="claude-work", agent_type="claude")
        config = GlobalConfig(container_runtime="")

        info = create_sandbox(
            tmpl, agent, str(tmp_path),
            name="sandboxer-test-sandboxes",
            config=config,
        )
        try:
            assert info.name == "sandboxer-test-sandboxes"
            assert info.template == "python-dev"
            assert info.agent == "claude-work"
            assert info.status == "running"
        finally:
            try:
                remove(info.name)
            except Exception:
                pass

    def test_create_auto_name(self, tmp_path) -> None:
        tmpl = SandboxTemplate(name="node")
        agent = AgentProfile(name="codex", agent_type="codex")
        config = GlobalConfig(container_runtime="")

        info = create_sandbox(tmpl, agent, str(tmp_path), config=config)
        try:
            assert info.name.startswith("sandboxer-")
            assert "node" in info.name
            assert "codex" in info.name
        finally:
            try:
                remove(info.name)
            except Exception:
                pass


class TestListRunning:
    def test_list_includes_sandbox(self, tmp_path) -> None:
        tmpl = SandboxTemplate(name="test")
        agent = AgentProfile(name="shell", agent_type="shell")
        config = GlobalConfig(container_runtime="")

        info = create_sandbox(
            tmpl, agent, str(tmp_path),
            name="sandboxer-test-list",
            config=config,
        )
        try:
            results = list_running_sandboxes()
            names = [r.name for r in results]
            assert info.name in names
        finally:
            try:
                remove(info.name)
            except Exception:
                pass


class TestGetSandboxStats:
    def test_returns_stats(self, tmp_path) -> None:
        tmpl = SandboxTemplate(name="stats-test")
        agent = AgentProfile(name="shell", agent_type="shell")
        config = GlobalConfig(container_runtime="")

        info = create_sandbox(
            tmpl, agent, str(tmp_path),
            name="sandboxer-test-stats",
            config=config,
        )
        try:
            stats = get_sandbox_stats(info.name)
            assert stats.name == info.name
        finally:
            try:
                remove(info.name)
            except Exception:
                pass
