"""Tests for sandboxer.cli — uses typer's CliRunner."""
from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from typer.testing import CliRunner

from sandboxer.cli import app
from sandboxer.core.agents import save_agent
from sandboxer.core.models import AgentProfile, SandboxTemplate
from sandboxer.core.templates import save_template

runner = CliRunner()


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestConfigCommand:
    def test_show_config(self, tmp_path: Path) -> None:
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, ["config"])
            assert result.exit_code == 0
            assert "Config dir:" in result.output
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

    @patch("sandboxer.core.docker.subprocess.run")
    def test_push_template(self, mock_run, tmp_path: Path) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(),  # docker tag
            _mock_run(),  # docker image push
        ]
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            save_template(
                SandboxTemplate(name="pushable", base_image="img:latest"),
                base=tmp_path,
            )
            result = runner.invoke(app, [
                "template", "push", "pushable", "registry.io/pushable:v1",
            ])
            assert result.exit_code == 0
            assert "Pushed" in result.output

    @patch("sandboxer.core.docker.subprocess.run")
    def test_pull_template(self, mock_run, tmp_path: Path) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(),  # docker image pull
        ]
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, [
                "template", "pull", "registry.io/sandbox:v2",
                "--as", "pulled-tmpl",
            ])
            assert result.exit_code == 0
            assert "Pulled" in result.output


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


class TestCleanupCommand:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_cleanup_dry_run(self, mock_run) -> None:
        # Mock docker availability check + sandbox ls.
        ls_output = (
            "NAME                          STATUS     IMAGE\n"
            "sandboxer-old-20260314        stopped    img:latest\n"
        )
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(stdout=ls_output),  # docker sandbox ls (orphans)
        ]
        with patch("sandboxer.core.metadata.list_metadata", return_value=[]):
            result = runner.invoke(app, ["cleanup", "--dry-run"])
            assert result.exit_code == 0
            assert "sandboxer-old-20260314" in result.output

    @patch("sandboxer.core.docker.subprocess.run")
    def test_cleanup_expired_flag(self, mock_run) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
        ]
        with patch("sandboxer.cli.find_expired", return_value=[]):
            result = runner.invoke(app, ["cleanup", "--expired", "--dry-run"])
            assert result.exit_code == 0
            assert "No matching" in result.output

    @patch("sandboxer.core.docker.subprocess.run")
    def test_cleanup_idle_flag(self, mock_run) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
        ]
        with patch("sandboxer.cli.find_idle", return_value=[]):
            result = runner.invoke(app, ["cleanup", "--idle", "--dry-run"])
            assert result.exit_code == 0
            assert "No matching" in result.output


class TestSandboxCreateCommand:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_validates_mount(self, mock_run, tmp_path: Path) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
        ]
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


class TestSandboxStatsCommand:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_stats(self, mock_run) -> None:
        stats_json = (
            '{"Name":"my-box","CPUPerc":"1.0%","MemUsage":"100MiB / 4GiB",'
            '"MemPerc":"2.5%","NetIO":"1kB / 2kB","BlockIO":"0B / 0B","PIDs":"5"}'
        )
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(stdout=stats_json),  # docker stats
        ]
        result = runner.invoke(app, ["sandbox", "stats", "my-box"])
        assert result.exit_code == 0
        assert "1.0%" in result.output
        assert "100MiB / 4GiB" in result.output


class TestSandboxSnapshotCommand:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_snapshot(self, mock_run) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(),  # docker sandbox save
        ]
        result = runner.invoke(app, [
            "sandbox", "snapshot", "my-box", "my-registry/snap:v1",
        ])
        assert result.exit_code == 0
        assert "Snapshot saved" in result.output

    @patch("sandboxer.core.docker.subprocess.run")
    def test_snapshot_with_register(self, mock_run, tmp_path: Path) -> None:
        mock_run.side_effect = [
            _mock_run(),  # docker info
            _mock_run(),  # docker sandbox --help
            _mock_run(),  # docker sandbox save
        ]
        with patch("sandboxer.core.config.config_dir", return_value=tmp_path):
            result = runner.invoke(app, [
                "sandbox", "snapshot", "my-box", "my-registry/snap:v1",
                "--register", "--as", "my-snap",
            ])
            assert result.exit_code == 0
            assert "Registered template: my-snap" in result.output
