"""Integration tests for sandbox orchestration — requires a container runtime.

Run with ``pytest -m integration``.
"""
from __future__ import annotations

import time

import pytest

from sandboxer.core.config import GlobalConfig
from sandboxer.core.docker import is_docker_available, remove
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.sandboxes import (
    create_sandbox,
    list_running_sandboxes,
    remove_sandbox,
    stop_sandbox,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_runtime():
    if not is_docker_available():
        pytest.skip("No container runtime available")


class TestSandboxOrchestrationReal:
    def test_create_and_list(self, tmp_path) -> None:
        tmpl = SandboxTemplate(name="integ-test")
        agent = AgentProfile(name="test-agent", agent_type="claude")
        config = GlobalConfig(container_runtime="")
        name = f"sandboxer-integ-orch-{int(time.time())}"

        try:
            info = create_sandbox(
                tmpl, agent, str(tmp_path), name=name, config=config,
            )
            assert info.name == name
            assert info.status == "running"

            running = list_running_sandboxes()
            names = [s.name for s in running]
            assert name in names
        finally:
            try:
                stop_sandbox(name)
            except Exception:
                pass
            try:
                remove_sandbox(name)
            except Exception:
                pass
