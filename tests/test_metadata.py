"""Tests for sandboxer.core.metadata."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from sandboxer.core.metadata import (
    SandboxMetadata,
    delete_metadata,
    list_metadata,
    load_metadata,
    save_metadata,
    touch_activity,
)


class TestMetadataCRUD:
    def test_save_and_load(self, tmp_path: Path) -> None:
        now = datetime.now()
        meta = SandboxMetadata(
            name="test-sandbox",
            created_at=now,
            last_activity=now,
            ttl_seconds=3600,
            idle_timeout_seconds=600,
        )
        save_metadata(meta, base=tmp_path)
        loaded = load_metadata("test-sandbox", base=tmp_path)
        assert loaded.name == "test-sandbox"
        assert loaded.ttl_seconds == 3600
        assert loaded.idle_timeout_seconds == 600

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="metadata not found"):
            load_metadata("nope", base=tmp_path)

    def test_delete(self, tmp_path: Path) -> None:
        now = datetime.now()
        meta = SandboxMetadata(
            name="to-delete", created_at=now, last_activity=now,
        )
        save_metadata(meta, base=tmp_path)
        delete_metadata("to-delete", base=tmp_path)
        with pytest.raises(FileNotFoundError):
            load_metadata("to-delete", base=tmp_path)

    def test_delete_nonexistent_is_noop(self, tmp_path: Path) -> None:
        delete_metadata("nonexistent", base=tmp_path)  # Should not raise.

    def test_list_metadata(self, tmp_path: Path) -> None:
        now = datetime.now()
        for name in ["alpha", "beta"]:
            save_metadata(
                SandboxMetadata(name=name, created_at=now, last_activity=now),
                base=tmp_path,
            )
        result = list_metadata(base=tmp_path)
        names = [m.name for m in result]
        assert "alpha" in names
        assert "beta" in names

    def test_list_empty(self, tmp_path: Path) -> None:
        result = list_metadata(base=tmp_path)
        assert result == []


class TestTouchActivity:
    def test_updates_last_activity(self, tmp_path: Path) -> None:
        old_time = datetime(2025, 1, 1, 12, 0, 0)
        meta = SandboxMetadata(
            name="active",
            created_at=old_time,
            last_activity=old_time,
        )
        save_metadata(meta, base=tmp_path)
        touch_activity("active", base=tmp_path)
        loaded = load_metadata("active", base=tmp_path)
        assert loaded.last_activity > old_time

    def test_touch_nonexistent_is_noop(self, tmp_path: Path) -> None:
        touch_activity("nonexistent", base=tmp_path)  # Should not raise.
