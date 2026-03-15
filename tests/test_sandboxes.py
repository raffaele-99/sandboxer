"""Tests for sandboxer.core.sandboxes."""
from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

from sandboxer.core.config import GlobalConfig
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.sandboxes import (
    create_sandbox,
    get_sandbox_stats,
    list_running_sandboxes,
    snapshot_sandbox,
)


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestCreateSandbox:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_with_defaults(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="sandboxer-test\n")
        tmpl = SandboxTemplate(name="python-dev")
        agent = AgentProfile(name="claude-work", agent_type="claude")
        config = GlobalConfig()

        info = create_sandbox(
            tmpl, agent, "/home/user/project",
            name="sandboxer-test",
            config=config,
        )
        assert info.name == "sandboxer-test"
        assert info.template == "python-dev"
        assert info.agent == "claude-work"
        assert info.status == "running"

    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_auto_name(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="auto-name\n")
        tmpl = SandboxTemplate(name="node")
        agent = AgentProfile(name="codex", agent_type="codex")
        config = GlobalConfig()

        info = create_sandbox(tmpl, agent, "/workspace", config=config)
        assert info.name.startswith("sandboxer-")
        assert "node" in info.name
        assert "codex" in info.name

    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_with_ttl(self, mock_run, tmp_path) -> None:
        mock_run.return_value = _mock_run(stdout="sandboxer-ttl\n")
        tmpl = SandboxTemplate(name="dev")
        agent = AgentProfile(name="claude", agent_type="claude")
        config = GlobalConfig()

        with patch("sandboxer.core.metadata.config_dir", return_value=tmp_path):
            info = create_sandbox(
                tmpl, agent, "/workspace",
                name="sandboxer-ttl",
                config=config,
                ttl_seconds=3600,
                idle_timeout_seconds=600,
            )
            assert info.name == "sandboxer-ttl"

            from sandboxer.core.metadata import load_metadata
            meta = load_metadata("sandboxer-ttl", base=tmp_path)
            assert meta.ttl_seconds == 3600
            assert meta.idle_timeout_seconds == 600


class TestListRunning:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_filters_by_prefix(self, mock_run) -> None:
        output = (
            "NAME                          STATUS     IMAGE\n"
            "sandboxer-py-dev-20260315     running    img:latest\n"
            "other-container               running    img:latest\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        results = list_running_sandboxes()
        assert len(results) == 1
        assert results[0].name == "sandboxer-py-dev-20260315"


class TestGetSandboxStats:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_returns_stats_model(self, mock_run) -> None:
        stats_json = (
            '{"Name":"my-box","CPUPerc":"0.5%","MemUsage":"50MiB / 2GiB",'
            '"MemPerc":"2.5%","NetIO":"1kB / 2kB","BlockIO":"0B / 0B","PIDs":"3"}'
        )
        mock_run.return_value = _mock_run(stdout=stats_json)
        stats = get_sandbox_stats("my-box")
        assert stats.name == "my-box"
        assert stats.cpu_percent == "0.5%"
        assert stats.pids == "3"


class TestSnapshotSandbox:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_snapshot(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        snapshot_sandbox("my-sandbox", "my-registry/snap:v1")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "sandbox", "save", "my-sandbox", "my-registry/snap:v1"]
