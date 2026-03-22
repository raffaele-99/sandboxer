"""Integration tests for container operations — requires a container runtime.

Run with ``pytest -m integration``.
"""
from __future__ import annotations

import time

import pytest

from sandboxer.core.docker import (
    DockerError,
    create,
    get_runtime,
    is_docker_available,
    list_sandboxes,
    remove,
    sandbox_exists,
    stop,
)

pytestmark = pytest.mark.integration

INTEGRATION_SANDBOX_PREFIX = "sandboxer-test-integ-"


@pytest.fixture(autouse=True)
def _require_runtime():
    if not is_docker_available():
        pytest.skip("No container runtime available")


@pytest.fixture()
def sandbox_name():
    """Yield a unique sandbox name and clean it up afterwards."""
    name = f"{INTEGRATION_SANDBOX_PREFIX}{int(time.time())}"
    yield name
    try:
        stop(name)
    except Exception:
        pass
    try:
        remove(name)
    except Exception:
        pass


class TestRuntimeAvailability:
    def test_runtime_is_available(self) -> None:
        assert is_docker_available() is True

    def test_runtime_detected(self) -> None:
        rt = get_runtime()
        assert rt.name in ("docker", "apple")


class TestListSandboxesReal:
    def test_list_returns_list(self) -> None:
        rows = list_sandboxes()
        assert isinstance(rows, list)


class TestSandboxLifecycleReal:
    def test_create_list_stop_remove(self, sandbox_name: str, tmp_path) -> None:
        """Full lifecycle: create -> verify listed -> stop -> remove."""
        returned_name = create(
            "alpine:latest",
            name=sandbox_name,
            volumes={str(tmp_path): "/mnt/workspace"},
        )
        assert returned_name == sandbox_name
        assert sandbox_exists(sandbox_name) is True

        stop(sandbox_name)
        remove(sandbox_name)
        assert sandbox_exists(sandbox_name) is False

    def test_create_with_read_only(self, sandbox_name: str, tmp_path) -> None:
        name = sandbox_name + "-ro"
        try:
            create(
                "alpine:latest",
                name=name,
                volumes={str(tmp_path): "/mnt/workspace:ro"},
            )
            assert sandbox_exists(name) is True
        finally:
            try:
                stop(name)
            except Exception:
                pass
            try:
                remove(name)
            except Exception:
                pass

    def test_remove_nonexistent_raises(self) -> None:
        with pytest.raises(DockerError):
            remove("sandboxer-test-does-not-exist-12345")

    def test_stop_nonexistent_raises(self) -> None:
        with pytest.raises(DockerError):
            stop("sandboxer-test-does-not-exist-12345")
