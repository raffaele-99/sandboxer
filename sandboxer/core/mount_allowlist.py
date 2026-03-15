"""Allowlist-based mount path validation.

The allowlist lives at ``~/.config/sandboxer/mount-allowlist.json`` — outside
any project root so sandboxes cannot modify their own access rules.
"""
from __future__ import annotations

import json
from pathlib import Path

from .config import BLOCKED_MOUNT_PATTERNS, config_dir


def _allowlist_path() -> Path:
    return config_dir() / "mount-allowlist.json"


def load_allowlist() -> list[str]:
    path = _allowlist_path()
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [str(p) for p in data]
    return []


def save_allowlist(paths: list[str]) -> None:
    path = _allowlist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(paths, indent=2) + "\n", encoding="utf-8")


def add_to_allowlist(host_path: str) -> list[str]:
    paths = load_allowlist()
    resolved = str(Path(host_path).resolve())
    if resolved not in paths:
        paths.append(resolved)
        save_allowlist(paths)
    return paths


def remove_from_allowlist(host_path: str) -> list[str]:
    paths = load_allowlist()
    resolved = str(Path(host_path).resolve())
    paths = [p for p in paths if p != resolved]
    save_allowlist(paths)
    return paths


def is_path_blocked(host_path: str) -> str | None:
    """Return the matching blocked pattern if the path is dangerous, else None."""
    resolved = Path(host_path).resolve()
    path_str = str(resolved)
    for pattern in BLOCKED_MOUNT_PATTERNS:
        if f"/{pattern}" in path_str or path_str.endswith(pattern):
            return pattern
    return None


def validate_mount(host_path: str) -> tuple[bool, str]:
    """Validate a mount path against the allowlist and blocklist.

    Returns ``(ok, reason)`` — if *ok* is False, *reason* explains why.
    """
    blocked = is_path_blocked(host_path)
    if blocked:
        return False, f"path matches blocked pattern: {blocked}"

    resolved = str(Path(host_path).resolve())
    if not Path(resolved).exists():
        return False, f"path does not exist: {resolved}"

    allowed = load_allowlist()
    if not allowed:
        # No allowlist configured — everything (non-blocked) is allowed.
        return True, "ok"

    for allowed_path in allowed:
        if resolved == allowed_path or resolved.startswith(allowed_path + "/"):
            return True, "ok"

    return False, f"path not in allowlist: {resolved}"
