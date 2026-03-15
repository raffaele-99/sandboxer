"""Tests for sandboxer.core.cleanup."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from sandboxer.core.cleanup import (
    cleanup_orphans,
    find_all_cleanup_candidates,
    find_expired,
    find_idle,
    find_orphans,
)
from sandboxer.core.metadata import SandboxMetadata, save_metadata


def _mock_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class TestFindOrphans:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_finds_stopped_sandboxer_containers(self, mock_run) -> None:
        output = (
            "NAME                          STATUS     IMAGE\n"
            "sandboxer-py-dev-20260315     running    img:latest\n"
            "sandboxer-old-thing-20260314  stopped    img:latest\n"
            "other-container               stopped    img:latest\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        orphans = find_orphans()
        assert orphans == ["sandboxer-old-thing-20260314"]

    @patch("sandboxer.core.docker.subprocess.run")
    def test_no_orphans(self, mock_run) -> None:
        output = (
            "NAME                          STATUS     IMAGE\n"
            "sandboxer-py-dev-20260315     running    img:latest\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        assert find_orphans() == []

    @patch("sandboxer.core.docker.subprocess.run")
    def test_ignores_non_sandboxer_containers(self, mock_run) -> None:
        output = (
            "NAME              STATUS     IMAGE\n"
            "my-container      stopped    img:latest\n"
        )
        mock_run.return_value = _mock_run(stdout=output)
        assert find_orphans() == []


class TestCleanupOrphans:
    @patch("sandboxer.core.docker.subprocess.run")
    def test_removes_specified_names(self, mock_run) -> None:
        mock_run.return_value = _mock_run()
        removed = cleanup_orphans(["sandboxer-old-1", "sandboxer-old-2"])
        assert removed == ["sandboxer-old-1", "sandboxer-old-2"]
        assert mock_run.call_count == 2

    @patch("sandboxer.core.docker.subprocess.run")
    def test_handles_removal_failure(self, mock_run) -> None:
        # First remove succeeds, second fails.
        mock_run.side_effect = [
            _mock_run(),
            _mock_run(returncode=1, stderr="error"),
        ]
        removed = cleanup_orphans(["good", "bad"])
        # "bad" raises DockerSandboxError which is caught.
        assert "good" in removed


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
    @patch("sandboxer.core.docker.subprocess.run")
    def test_returns_all_categories(self, mock_run) -> None:
        mock_run.return_value = _mock_run(
            stdout="NAME              STATUS     IMAGE\n"
        )
        with patch("sandboxer.core.metadata.list_metadata", return_value=[]):
            result = find_all_cleanup_candidates()
        assert "orphans" in result
        assert "expired" in result
        assert "idle" in result
