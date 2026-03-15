"""Integration tests that run real ``docker sandbox`` commands.

These tests are skipped unless Docker Desktop with sandbox support is
available.  Run with ``pytest -m integration`` to select only these, or
they'll run automatically as part of the full suite on capable machines.
"""
from __future__ import annotations

import subprocess

import pytest

from sandboxer.core.docker import (
    DockerSandboxError,
    create,
    is_docker_available,
    is_sandbox_feature_available,
    list_sandboxes,
    remove,
    sandbox_exists,
    stop,
)

_docker_ok = is_docker_available()
_sandbox_ok = _docker_ok and is_sandbox_feature_available()

skip_no_docker = pytest.mark.skipif(
    not _docker_ok, reason="Docker engine not available"
)
skip_no_sandbox = pytest.mark.skipif(
    not _sandbox_ok, reason="docker sandbox not available (needs Docker Desktop 4.58+)"
)

pytestmark = [pytest.mark.integration, skip_no_sandbox]


INTEGRATION_SANDBOX_PREFIX = "sandboxer-test-integ-"


@pytest.fixture()
def sandbox_name():
    """Yield a unique sandbox name and clean it up afterwards."""
    import time

    name = f"{INTEGRATION_SANDBOX_PREFIX}{int(time.time())}"
    yield name
    # Teardown: best-effort cleanup.
    try:
        stop(name)
    except Exception:
        pass
    try:
        remove(name)
    except Exception:
        pass


class TestDockerAvailabilityReal:
    """Verify the availability helpers return True on a capable machine."""

    @skip_no_docker
    def test_docker_is_available(self) -> None:
        assert is_docker_available() is True

    def test_sandbox_feature_is_available(self) -> None:
        assert is_sandbox_feature_available() is True


class TestListSandboxesReal:
    def test_list_returns_list(self) -> None:
        """``list_sandboxes`` should return a list (possibly empty) without error."""
        rows = list_sandboxes()
        assert isinstance(rows, list)


class TestSandboxLifecycleReal:
    def test_create_list_stop_remove(self, sandbox_name: str, tmp_path) -> None:
        """Full lifecycle: create → verify listed → stop → remove."""
        workspace = str(tmp_path)

        # Create a sandbox using the default sandbox template.
        returned_name = create(
            template="",
            workspace=workspace,
            name=sandbox_name,
        )
        assert returned_name  # should return something non-empty

        # Verify it shows up in the list.
        assert sandbox_exists(sandbox_name) is True

        # Stop it.
        stop(sandbox_name)

        # Remove it.
        remove(sandbox_name)

        # Verify it's gone.
        assert sandbox_exists(sandbox_name) is False

    def test_create_with_read_only(self, sandbox_name: str, tmp_path) -> None:
        """Create a sandbox with read-only workspace mount."""
        workspace = str(tmp_path)
        name = sandbox_name + "-ro"

        try:
            create(
                template="",
                workspace=workspace,
                name=name,
                read_only=True,
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
        """Removing a sandbox that doesn't exist should raise."""
        with pytest.raises(DockerSandboxError):
            remove("sandboxer-test-does-not-exist-12345")

    def test_stop_nonexistent_raises(self) -> None:
        """Stopping a sandbox that doesn't exist should raise."""
        with pytest.raises(DockerSandboxError):
            stop("sandboxer-test-does-not-exist-12345")
