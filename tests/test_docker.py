"""Tests for sandboxer.core.docker — subprocess calls are mocked."""
from __future__ import annotations

from subprocess import CompletedProcess
from unittest.mock import patch

import pytest

from sandboxer.core.docker import (
    DockerSandboxError,
    SandboxRow,
    build_template,
    create,
    is_docker_available,
    is_sandbox_feature_available,
    list_sandboxes,
    pull_image,
    push_image,
    remove,
    sandbox_exists,
    sandbox_stats,
    save_as_template,
    stop,
    tag_image,
)


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestCreate:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_basic_create(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="my-sandbox\n")
        name = create("my-template:latest", "/home/user/project", name="my-sandbox")
        assert name == "my-sandbox"
        cmd = mock_run.call_args[0][0]
        assert cmd[:2] == ["docker", "sandbox"]
        assert "run" in cmd
        assert "-t" in cmd
        assert "my-template:latest" in cmd
        assert "--name" in cmd

    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_read_only(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="ro-box\n")
        create("tmpl", "/workspace", name="ro-box", read_only=True)
        cmd = mock_run.call_args[0][0]
        assert any(arg.endswith(":ro") for arg in cmd)

    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_failure(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1, stderr="no such template")
        with pytest.raises(DockerSandboxError, match="no such template"):
            create("bad-template", "/workspace")

    @patch("sandboxer.core.docker.subprocess.run")
    def test_create_no_extra_args(self, mock_run) -> None:
        """docker sandbox run only supports --name and -t, no extra flags."""
        mock_run.return_value = _mock_run(stdout="basic-box\n")
        result = create("tmpl", "/workspace", name="basic-box")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "sandbox", "run", "-t", "tmpl", "--name", "basic-box", "/workspace"]
        assert result == "basic-box"


class TestListSandboxes:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_parse_table_output(self, mock_run) -> None:
        output = (
            "NAME                STATUS     IMAGE\n"
            "sandboxer-py-dev    running    docker/sandbox-templates:latest\n"
            "sandboxer-node      stopped    docker/sandbox-templates:node\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        rows = list_sandboxes()
        assert len(rows) == 2
        assert rows[0] == SandboxRow(
            name="sandboxer-py-dev",
            status="running",
            image="docker/sandbox-templates:latest",
        )
        assert rows[1].status == "stopped"

    @patch("sandboxer.core.docker.subprocess.run")
    def test_empty_output(self, mock_run) -> None:
        mock_run.return_value = _mock_run(stdout="NAME  STATUS  IMAGE\n")
        rows = list_sandboxes()
        assert rows == []

    @patch("sandboxer.core.docker.subprocess.run")
    def test_command_failure(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1, stderr="not supported")
        rows = list_sandboxes()
        assert rows == []


class TestStopAndRemove:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_stop(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        stop("my-sandbox")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "sandbox", "stop", "my-sandbox"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_remove(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        remove("my-sandbox")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "sandbox", "rm", "my-sandbox"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_stop_failure(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1, stderr="no such sandbox")
        with pytest.raises(DockerSandboxError):
            stop("nonexistent")


class TestSaveAsTemplate:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_save(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        save_as_template("my-sandbox", "my-registry/my-template:v1")
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "docker", "sandbox", "save",
            "my-sandbox", "my-registry/my-template:v1",
        ]


class TestBuildTemplate:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_build(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        build_template("/tmp/Dockerfile", "my-image:latest", "/tmp")
        cmd = mock_run.call_args[0][0]
        assert cmd == [
            "docker", "build", "-t", "my-image:latest",
            "-f", "/tmp/Dockerfile", "/tmp",
        ]


class TestSandboxExists:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_exists(self, mock_run) -> None:
        output = (
            "NAME              STATUS     IMAGE\n"
            "my-sandbox        running    img:latest\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        assert sandbox_exists("my-sandbox") is True

    @patch("sandboxer.core.docker.subprocess.run")
    def test_not_exists(self, mock_run) -> None:
        output = "NAME  STATUS  IMAGE\n"
        mock_run.return_value = _mock_run(stdout=output)
        assert sandbox_exists("nope") is False


class TestSandboxStats:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_stats(self, mock_run) -> None:
        stats_json = (
            '{"Name":"my-sandbox","CPUPerc":"1.23%","MemUsage":"100MiB / 4GiB",'
            '"MemPerc":"2.50%","NetIO":"1kB / 2kB","BlockIO":"3kB / 4kB","PIDs":"5"}'
        )
        mock_run.return_value = _mock_run(stdout=stats_json)
        result = sandbox_stats("my-sandbox")
        assert result["name"] == "my-sandbox"
        assert result["cpu_percent"] == "1.23%"
        assert result["mem_usage"] == "100MiB / 4GiB"
        assert result["pids"] == "5"
        cmd = mock_run.call_args[0][0]
        assert cmd[:2] == ["docker", "stats"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_stats_failure(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1, stderr="no such container")
        with pytest.raises(DockerSandboxError):
            sandbox_stats("nonexistent")


class TestImageOperations:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_tag_image(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        tag_image("source:latest", "target:v1")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "tag", "source:latest", "target:v1"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_push_image(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        push_image("myregistry/img:v1")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "image", "push", "myregistry/img:v1"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_pull_image(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        pull_image("myregistry/img:v1")
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "image", "pull", "myregistry/img:v1"]


class TestDockerAvailability:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_docker_available(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        assert is_docker_available() is True

    @patch("sandboxer.core.docker.subprocess.run")
    def test_docker_not_available(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1)
        assert is_docker_available() is False

    @patch("sandboxer.core.docker.subprocess.run", side_effect=FileNotFoundError)
    def test_docker_not_installed(self, mock_run) -> None:
        assert is_docker_available() is False

    @patch("sandboxer.core.docker.subprocess.run")
    def test_sandbox_feature_available(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        assert is_sandbox_feature_available() is True

    @patch("sandboxer.core.docker.subprocess.run")
    def test_sandbox_feature_not_available(self, mock_run) -> None:
        mock_run.return_value = _mock_run(returncode=1)
        assert is_sandbox_feature_available() is False
