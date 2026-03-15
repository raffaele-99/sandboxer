"""Tests for sandboxer.core.templates."""
from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from sandboxer.core.models import SandboxTemplate
from sandboxer.core.templates import (
    delete_template,
    list_templates,
    load_template,
    pull_template,
    push_template,
    render_dockerfile,
    save_template,
)


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestTemplateCRUD:
    def test_save_and_load(self, tmp_path: Path) -> None:
        tmpl = SandboxTemplate(
            name="python-dev",
            description="Python dev env",
            base_image="docker/sandbox-templates:latest",
            packages=["vim", "git"],
            pip_packages=["pytest", "ruff"],
        )
        save_template(tmpl, base=tmp_path)

        loaded = load_template("python-dev", base=tmp_path)
        assert loaded.name == "python-dev"
        assert loaded.packages == ["vim", "git"]
        assert loaded.pip_packages == ["pytest", "ruff"]

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        import pytest

        with pytest.raises(FileNotFoundError, match="template not found"):
            load_template("nope", base=tmp_path)

    def test_delete(self, tmp_path: Path) -> None:
        tmpl = SandboxTemplate(name="temp", base_image="ubuntu:24.04")
        save_template(tmpl, base=tmp_path)
        assert (tmp_path / "templates" / "temp.yml").exists()
        assert (tmp_path / "templates" / "temp.Dockerfile").exists()

        delete_template("temp", base=tmp_path)
        assert not (tmp_path / "templates" / "temp.yml").exists()
        assert not (tmp_path / "templates" / "temp.Dockerfile").exists()

    def test_list_templates(self, tmp_path: Path) -> None:
        for name in ["alpha", "beta", "gamma"]:
            save_template(SandboxTemplate(name=name), base=tmp_path)

        result = list_templates(base=tmp_path)
        names = [t.name for t in result]
        assert names == ["alpha", "beta", "gamma"]

    def test_list_empty(self, tmp_path: Path) -> None:
        result = list_templates(base=tmp_path)
        assert result == []


class TestRenderDockerfile:
    def test_minimal(self) -> None:
        tmpl = SandboxTemplate(name="minimal")
        df = render_dockerfile(tmpl)
        assert df.startswith("FROM docker/sandbox-templates:latest")

    def test_with_packages(self) -> None:
        tmpl = SandboxTemplate(name="test", packages=["vim", "curl"])
        df = render_dockerfile(tmpl)
        assert "apt-get install" in df
        assert "vim" in df
        assert "curl" in df

    def test_with_pip_packages(self) -> None:
        tmpl = SandboxTemplate(name="test", pip_packages=["pytest", "ruff"])
        df = render_dockerfile(tmpl)
        assert "pip install" in df
        assert "pytest" in df

    def test_with_npm_packages(self) -> None:
        tmpl = SandboxTemplate(name="test", npm_packages=["prettier"])
        df = render_dockerfile(tmpl)
        assert "npm install -g" in df
        assert "prettier" in df

    def test_with_custom_lines(self) -> None:
        tmpl = SandboxTemplate(
            name="test",
            custom_dockerfile_lines=["RUN echo hello", "COPY myfile /app/"],
        )
        df = render_dockerfile(tmpl)
        assert "RUN echo hello" in df
        assert "COPY myfile /app/" in df

    def test_combined(self) -> None:
        tmpl = SandboxTemplate(
            name="full",
            base_image="docker/sandbox-templates:claude-code",
            packages=["git"],
            pip_packages=["flask"],
            npm_packages=["typescript"],
            custom_dockerfile_lines=["ENV MY_VAR=1"],
        )
        df = render_dockerfile(tmpl)
        assert df.startswith("FROM docker/sandbox-templates:claude-code")
        assert "apt-get install" in df
        assert "pip install" in df
        assert "npm install" in df
        assert "ENV MY_VAR=1" in df

    def test_with_agent_type_claude(self) -> None:
        tmpl = SandboxTemplate(name="claude-tmpl", agent_type="claude")
        df = render_dockerfile(tmpl)
        assert "claude-code" in df
        assert "npm install -g" in df

    def test_with_agent_type_codex(self) -> None:
        tmpl = SandboxTemplate(name="codex-tmpl", agent_type="codex")
        df = render_dockerfile(tmpl)
        assert "codex" in df.lower()

    def test_agent_type_after_npm_before_custom(self) -> None:
        tmpl = SandboxTemplate(
            name="order-test",
            npm_packages=["prettier"],
            agent_type="claude",
            custom_dockerfile_lines=["ENV CUSTOM=1"],
        )
        df = render_dockerfile(tmpl)
        prettier_pos = df.index("prettier")
        claude_pos = df.index("claude-code")
        custom_pos = df.index("ENV CUSTOM=1")
        assert prettier_pos < claude_pos < custom_pos

    def test_no_agent_type_backwards_compatible(self) -> None:
        tmpl = SandboxTemplate(name="compat", packages=["vim"])
        df = render_dockerfile(tmpl)
        assert "claude" not in df
        assert "codex" not in df


class TestTemplateMarketplace:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_push_template(self, mock_run, tmp_path: Path) -> None:
        mock_run.return_value = _mock_run()
        save_template(
            SandboxTemplate(name="pushable", base_image="img:latest"),
            base=tmp_path,
        )
        push_template("pushable", "registry.io/pushable:v1", base=tmp_path)

        # Verify image was tagged and pushed.
        calls = [c[0][0] for c in mock_run.call_args_list]
        assert ["docker", "tag", "img:latest", "registry.io/pushable:v1"] in calls
        assert ["docker", "image", "push", "registry.io/pushable:v1"] in calls

        # Verify registry_source was saved.
        loaded = load_template("pushable", base=tmp_path)
        assert loaded.registry_source == "registry.io/pushable:v1"

    @patch("sandboxer.core.docker.subprocess.run")
    def test_pull_template(self, mock_run, tmp_path: Path) -> None:
        mock_run.return_value = _mock_run()
        tmpl = pull_template("registry.io/sandbox:v2", "pulled-tmpl", base=tmp_path)
        assert tmpl.name == "pulled-tmpl"
        assert tmpl.base_image == "registry.io/sandbox:v2"
        assert tmpl.registry_source == "registry.io/sandbox:v2"

        # Verify image was pulled.
        cmd = mock_run.call_args[0][0]
        assert cmd == ["docker", "image", "pull", "registry.io/sandbox:v2"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_pull_template_auto_name(self, mock_run, tmp_path: Path) -> None:
        mock_run.return_value = _mock_run()
        tmpl = pull_template("registry.io/my-sandbox:v1", base=tmp_path)
        assert tmpl.name == "my-sandbox"
