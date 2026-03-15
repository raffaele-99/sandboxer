"""Integration tests for orphan cleanup with real docker sandbox calls.

Skipped unless Docker Desktop with sandbox support is available.
"""
from __future__ import annotations

import time

import pytest

from sandboxer.core.cleanup import find_orphans
from sandboxer.core.docker import (
    create,
    is_docker_available,
    is_sandbox_feature_available,
    remove,
    stop,
)

_sandbox_ok = is_docker_available() and is_sandbox_feature_available()

skip_no_sandbox = pytest.mark.skipif(
    not _sandbox_ok, reason="docker sandbox not available"
)

pytestmark = [pytest.mark.integration, skip_no_sandbox]


class TestFindOrphansReal:
    def test_find_orphans_returns_list(self) -> None:
        """find_orphans should return a list without error."""
        result = find_orphans()
        assert isinstance(result, list)

    def test_stopped_sandbox_detected_as_orphan(self, tmp_path) -> None:
        """A stopped sandboxer-prefixed sandbox should be found as an orphan."""
        name = f"sandboxer-orphan-test-{int(time.time())}"
        try:
            create(template="", workspace=str(tmp_path), name=name)
            stop(name)

            orphans = find_orphans()
            assert name in orphans
        finally:
            try:
                remove(name)
            except Exception:
                pass
