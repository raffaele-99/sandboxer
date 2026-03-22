"""Tests for sandboxer.core.cleanup.

Integration tests (FindOrphans, CleanupOrphans) require a container runtime.
TTL/idle tests use mocked metadata.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from sandboxer.core.cleanup import (
    cleanup_orphans,
    find_all_cleanup_candidates,
    find_expired,
    find_idle,
    find_orphans,
)
from sandboxer.core.docker import create, is_docker_available, remove, stop
from sandboxer.core.metadata import SandboxMetadata, save_metadata


@pytest.mark.integration
class TestFindOrphans:
    @pytest.fixture(autouse=True)
    def _require_runtime(self):
        if not is_docker_available():
            pytest.skip("No container runtime available")

    def test_finds_stopped_sandboxer_containers(self) -> None:
        name = create("alpine:latest", name="sandboxer-test-orphan")
        try:
            stop(name)
            orphans = find_orphans()
            assert name in orphans
        finally:
            try:
                remove(name)
            except Exception:
                pass

    def test_running_not_orphan(self) -> None:
        name = create("alpine:latest", name="sandboxer-test-running")
        try:
            orphans = find_orphans()
            assert name not in orphans
        finally:
            try:
                remove(name)
            except Exception:
                pass


@pytest.mark.integration
class TestCleanupOrphans:
    @pytest.fixture(autouse=True)
    def _require_runtime(self):
        if not is_docker_available():
            pytest.skip("No container runtime available")

    def test_removes_stopped_containers(self) -> None:
        name = create("alpine:latest", name="sandboxer-test-cleanup")
        stop(name)
        removed = cleanup_orphans([name])
        assert name in removed

        from sandboxer.core.docker import sandbox_exists
        assert not sandbox_exists(name)


class TestFindExpired:
    def test_finds_expired_sandbox(self, tmp_path: Path) -> None:
        old_time = datetime(2025, 1, 1, 12, 0, 0)
        meta = SandboxMetadata(
            name="expired-box",
            created_at=old_time,
            last_activity=old_time,
            ttl_seconds=3600,
        )
        save_metadata(meta, base=tmp_path)

        now = old_time + timedelta(seconds=7200)
        with patch("sandboxer.core.metadata.list_metadata", return_value=[meta]):
            expired = find_expired(now)
        assert "expired-box" in expired

    def test_not_expired_yet(self, tmp_path: Path) -> None:
        now = datetime.now()
        meta = SandboxMetadata(
            name="fresh-box",
            created_at=now,
            last_activity=now,
            ttl_seconds=3600,
        )
        with patch("sandboxer.core.metadata.list_metadata", return_value=[meta]):
            expired = find_expired(now + timedelta(seconds=60))
        assert expired == []

    def test_no_ttl_not_expired(self) -> None:
        now = datetime.now()
        meta = SandboxMetadata(
            name="no-ttl", created_at=now, last_activity=now,
        )
        with patch("sandboxer.core.metadata.list_metadata", return_value=[meta]):
            assert find_expired(now) == []


class TestFindIdle:
    def test_finds_idle_sandbox(self) -> None:
        old_time = datetime(2025, 1, 1, 12, 0, 0)
        meta = SandboxMetadata(
            name="idle-box",
            created_at=old_time,
            last_activity=old_time,
            idle_timeout_seconds=600,
        )
        now = old_time + timedelta(seconds=1200)
        with patch("sandboxer.core.metadata.list_metadata", return_value=[meta]):
            idle = find_idle(now)
        assert "idle-box" in idle

    def test_not_idle_yet(self) -> None:
        now = datetime.now()
        meta = SandboxMetadata(
            name="active-box",
            created_at=now,
            last_activity=now,
            idle_timeout_seconds=600,
        )
        with patch("sandboxer.core.metadata.list_metadata", return_value=[meta]):
            assert find_idle(now + timedelta(seconds=60)) == []


class TestFindAllCleanupCandidates:
    @pytest.mark.integration
    def test_returns_all_categories(self) -> None:
        if not is_docker_available():
            pytest.skip("No container runtime available")
        with patch("sandboxer.core.metadata.list_metadata", return_value=[]):
            result = find_all_cleanup_candidates()
        assert "orphans" in result
        assert "expired" in result
        assert "idle" in result
