"""Orphan sandbox detection and cleanup, plus TTL/idle expiry."""
from __future__ import annotations

from datetime import datetime

from .config import SANDBOX_NAME_PREFIX
from .docker import list_sandboxes, remove


def find_orphans() -> list[str]:
    """Return names of sandboxer-managed sandboxes that are stopped/exited."""
    orphans: list[str] = []
    for row in list_sandboxes():
        if not row.name.startswith(SANDBOX_NAME_PREFIX):
            continue
        status = row.status.lower()
        if status in ("stopped", "exited", "dead"):
            orphans.append(row.name)
    return orphans


def cleanup_orphans(names: list[str] | None = None) -> list[str]:
    """Remove orphaned sandboxes. Returns the names that were removed."""
    targets = names if names is not None else find_orphans()
    removed: list[str] = []
    for name in targets:
        try:
            remove(name)
            removed.append(name)
        except Exception:
            continue
    return removed


def find_expired(now: datetime | None = None) -> list[str]:
    """Return sandbox names that have exceeded their TTL."""
    from .metadata import list_metadata

    now = now or datetime.now()
    expired: list[str] = []
    for meta in list_metadata():
        if meta.ttl_seconds is not None:
            elapsed = (now - meta.created_at).total_seconds()
            if elapsed > meta.ttl_seconds:
                expired.append(meta.name)
    return expired


def find_idle(now: datetime | None = None) -> list[str]:
    """Return sandbox names that have exceeded their idle timeout."""
    from .metadata import list_metadata

    now = now or datetime.now()
    idle: list[str] = []
    for meta in list_metadata():
        if meta.idle_timeout_seconds is not None:
            idle_time = (now - meta.last_activity).total_seconds()
            if idle_time > meta.idle_timeout_seconds:
                idle.append(meta.name)
    return idle


def find_all_cleanup_candidates(now: datetime | None = None) -> dict[str, list[str]]:
    """Return all cleanup candidates grouped by category."""
    now = now or datetime.now()
    return {
        "orphans": find_orphans(),
        "expired": find_expired(now),
        "idle": find_idle(now),
    }
