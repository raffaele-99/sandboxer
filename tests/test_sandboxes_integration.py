"""Integration tests for sandbox orchestration with real docker calls.

Skipped unless Docker Desktop with sandbox support is available.
"""
from __future__ import annotations

import time

import pytest

from sandboxer.core.config import GlobalConfig
from sandboxer.core.docker import (
    is_docker_available,
    is_sandbox_feature_available,
    remove,
    stop,
)
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.sandboxes import (
    create_sandbox,
    list_running_sandboxes,
    remove_sandbox,
    stop_sandbox,
)

_sandbox_ok = is_docker_available() and is_sandbox_feature_available()

skip_no_sandbox = pytest.mark.skipif(
    not _sandbox_ok, reason="docker sandbox not available"
)

pytestmark = [pytest.mark.integration, skip_no_sandbox]


class TestSandboxOrchestrationReal:
    def test_create_and_list(self, tmp_path) -> None:
        """Create a sandbox via the orchestration layer and verify it's listed."""
        tmpl = SandboxTemplate(name="integ-test")
        agent = AgentProfile(name="test-agent", agent_type="claude")
        config = GlobalConfig()
        name = f"sandboxer-integ-orch-{int(time.time())}"

        try:
            info = create_sandbox(
                tmpl, agent, str(tmp_path), name=name, config=config,
            )
            assert info.name == name
            assert info.status == "running"

            # Should appear in the filtered list.
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
