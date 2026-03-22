"""Tests for sandboxer.cli — uses typer's CliRunner.

Tests that require container operations are marked as integration tests.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from sandboxer.cli import app
from sandboxer.core.agents import save_agent
from sandboxer.core.docker import is_docker_available
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.templates import save_template

runner = CliRunner()


class TestConfigCommand:
    def test_show_config(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, ["config"])
            assert result.exit_code == 0
            assert "Config dir:" in result.output
            assert "Container backend:" in result.output
            assert "Default TTL:" in result.output
            assert "Default idle timeout:" in result.output


class TestTemplateCommands:
    def test_create_and_list(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, [
                "template", "create", "test-tmpl",
                "--base", "ubuntu:24.04",
                "--desc", "Test template",
            ])
            assert result.exit_code == 0
            assert "Template saved" in result.output

            result = runner.invoke(app, ["template", "ls"])
            assert result.exit_code == 0
            assert "test-tmpl" in result.output

    def test_create_with_agent_type(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, [
                "template", "create", "claude-tmpl",
                "--agent-type", "claude",
            ])
            assert result.exit_code == 0
            assert "Template saved" in result.output

    def test_show_template(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            save_template(
                SandboxTemplate(name="show-me", description="visible"),
                base=tmp_path,
            )
            result = runner.invoke(app, ["template", "show", "show-me"])
            assert result.exit_code == 0
            assert "show-me" in result.output

    def test_show_nonexistent(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, ["template", "show", "nope"])
            assert result.exit_code == 1

    def test_delete_template(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            save_template(SandboxTemplate(name="to-delete"), base=tmp_path)
            result = runner.invoke(app, ["template", "rm", "to-delete"])
            assert result.exit_code == 0
            assert "Deleted" in result.output


class TestAgentCommands:
    def test_create_and_list(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, [
                "agent", "create", "my-claude",
                "--type", "claude",
            ])
            assert result.exit_code == 0
            assert "Agent profile saved" in result.output

            result = runner.invoke(app, ["agent", "ls"])
            assert result.exit_code == 0
            assert "my-claude" in result.output

    def test_delete_agent(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            save_agent(
                AgentProfile(name="to-delete", agent_type="codex"),
                base=tmp_path,
            )
            result = runner.invoke(app, ["agent", "rm", "to-delete"])
            assert result.exit_code == 0


class TestMountCommands:
    def test_ls_empty(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=tmp_path / "al.json"):
            result = runner.invoke(app, ["mount", "ls"])
            assert result.exit_code == 0
            assert "No allowlist" in result.output

    def test_add_and_ls(self, tmp_path: Path) -> None:
        al_file = tmp_path / "allowlist.json"
        with patch("sandboxer.core.mount_allowlist._allowlist_path", return_value=al_file):
            result = runner.invoke(app, ["mount", "add", str(tmp_path)])
            assert result.exit_code == 0
            assert "updated" in result.output

            result = runner.invoke(app, ["mount", "ls"])
            assert result.exit_code == 0
            assert str(tmp_path) in result.output


class TestSandboxCreateCommand:
    def test_create_validates_mount(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            save_template(SandboxTemplate(name="tmpl"), base=tmp_path)
            save_agent(
                AgentProfile(name="ag", agent_type="claude"),
                base=tmp_path,
            )
            # Mount path that doesn't exist.
            result = runner.invoke(app, [
                "sandbox", "create", "tmpl", "ag",
                "-w", "/nonexistent/path/xyz",
            ])
            assert result.exit_code == 1


@pytest.mark.integration
class TestSandboxStatsCommand:
    @pytest.fixture(autouse=True)
    def _require_runtime(self):
        if not is_docker_available():
            pytest.skip("No container runtime available")

    def test_stats(self, tmp_path: Path) -> None:
        from sandboxer.core.config import GlobalConfig
        from sandboxer.core.docker import create, remove
        from sandboxer.core.models import AgentProfile, SandboxTemplate

        name = create("alpine:latest", name="sandboxer-test-cli-stats")
        try:
            result = runner.invoke(app, ["sandbox", "stats", name])
            assert result.exit_code == 0
            assert "CPU:" in result.output
        finally:
            try:
                remove(name)
            except Exception:
                pass


@pytest.mark.integration
class TestSandboxSnapshotCommand:
    @pytest.fixture(autouse=True)
    def _require_runtime(self):
        if not is_docker_available():
            pytest.skip("No container runtime available")

    def test_snapshot(self) -> None:
        from sandboxer.core.docker import create, remove

        name = create("alpine:latest", name="sandboxer-test-cli-snap")
        try:
            result = runner.invoke(app, [
                "sandbox", "snapshot", name, "sandboxer-test-snap:v1",
            ])
            assert result.exit_code == 0
            assert "Snapshot saved" in result.output
        finally:
            try:
                remove(name)
            except Exception:
                pass

    def test_snapshot_with_register(self, tmp_path: Path) -> None:
        from sandboxer.core.docker import create, remove

        name = create("alpine:latest", name="sandboxer-test-cli-snap2")
        try:
            with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
                result = runner.invoke(app, [
                    "sandbox", "snapshot", name, "sandboxer-test-snap:v2",
                    "--register", "--as", "my-snap",
                ])
                assert result.exit_code == 0
                assert "Registered template: my-snap" in result.output
        finally:
            try:
                remove(name)
            except Exception:
                pass
