"""Integration tests for sandboxer.core.docker — requires a container runtime."""
from __future__ import annotations

import pytest

from sandboxer.core.docker import (
    DockerError,
    create,
    get_runtime,
    is_docker_available,
    list_sandboxes,
    remove,
    sandbox_exists,
    sandbox_stats,
    stop,
)

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_runtime():
    if not is_docker_available():
        pytest.skip("No container runtime available")


@pytest.fixture()
def sandbox():
    """Create a temporary sandbox and clean it up after the test."""
    name = create(
        "alpine:latest",
        name="sandboxer-test-docker",
        labels={"sandboxer.agent": "shell"},
    )
    yield name
    try:
        remove(name)
    except Exception:
        pass


class TestRuntime:
    def test_get_runtime(self) -> None:
        rt = get_runtime()
        assert rt.name in ("docker", "apple")
        assert rt.binary in ("docker", "container")


class TestCreate:
    def test_basic_create_and_remove(self) -> None:
        name = create("alpine:latest", name="sandboxer-test-create")
        try:
            assert name == "sandboxer-test-create"
            assert sandbox_exists(name)
        finally:
            remove(name)

    def test_create_with_volumes(self, tmp_path) -> None:
        name = create(
            "alpine:latest",
            name="sandboxer-test-vols",
            volumes={str(tmp_path): "/mnt/test"},
        )
        try:
            assert sandbox_exists(name)
        finally:
            remove(name)

    def test_create_readonly_volume(self, tmp_path) -> None:
        name = create(
            "alpine:latest",
            name="sandboxer-test-ro",
            volumes={str(tmp_path): "/mnt/test:ro"},
        )
        try:
            assert sandbox_exists(name)
        finally:
            remove(name)


class TestListSandboxes:
    def test_list_includes_managed(self, sandbox) -> None:
        rows = list_sandboxes()
        names = [r.name for r in rows]
        assert sandbox in names

    def test_list_returns_labels(self, sandbox) -> None:
        rows = list_sandboxes()
        row = next(r for r in rows if r.name == sandbox)
        assert row.agent == "shell"


class TestStopAndRemove:
    def test_stop(self, sandbox) -> None:
        stop(sandbox)
        rows = list_sandboxes()
        row = next(r for r in rows if r.name == sandbox)
        assert row.status in ("exited", "stopped")

    def test_remove(self) -> None:
        name = create("alpine:latest", name="sandboxer-test-rm")
        remove(name)
        assert not sandbox_exists(name)

    def test_stop_nonexistent(self) -> None:
        with pytest.raises(DockerError):
            stop("sandboxer-nonexistent-xyz")


class TestSandboxStats:
    def test_stats(self, sandbox) -> None:
        result = sandbox_stats(sandbox)
        assert result["name"] == sandbox
        assert "cpu_percent" in result


class TestSandboxExists:
    def test_exists(self, sandbox) -> None:
        assert sandbox_exists(sandbox) is True

    def test_not_exists(self) -> None:
        assert sandbox_exists("sandboxer-nonexistent-xyz") is False
