"""Integration tests for orphan cleanup — requires a container runtime.

Run with ``pytest -m integration``.
"""
from __future__ import annotations

import time

import pytest

from sandboxer.core.cleanup import find_orphans
from sandboxer.core.docker import create, is_docker_available, remove, stop

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _require_runtime():
    if not is_docker_available():
        pytest.skip("No container runtime available")


class TestFindOrphansReal:
    def test_find_orphans_returns_list(self) -> None:
        result = find_orphans()
        assert isinstance(result, list)

    def test_stopped_sandbox_detected_as_orphan(self, tmp_path) -> None:
        name = f"sandboxer-orphan-test-{int(time.time())}"
        try:
            create("alpine:latest", name=name)
            stop(name)

            orphans = find_orphans()
            assert name in orphans
        finally:
            try:
                remove(name)
            except Exception:
                pass
