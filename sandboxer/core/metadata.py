"""Sandbox metadata — tracks creation time, TTL, and idle timeouts."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from .config import config_dir


class SandboxMetadata(BaseModel):
    name: str
    created_at: datetime
    last_activity: datetime
    ttl_seconds: int | None = None
    idle_timeout_seconds: int | None = None


def _metadata_dir(base: Path | None = None) -> Path:
    d = (base or config_dir()) / "metadata"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _metadata_path(name: str, base: Path | None = None) -> Path:
    return _metadata_dir(base) / f"{name}.json"


def save_metadata(meta: SandboxMetadata, base: Path | None = None) -> Path:
    path = _metadata_path(meta.name, base)
    path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_metadata(name: str, base: Path | None = None) -> SandboxMetadata:
    path = _metadata_path(name, base)
    if not path.exists():
        raise FileNotFoundError(f"metadata not found: {name}")
    return SandboxMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def delete_metadata(name: str, base: Path | None = None) -> None:
    path = _metadata_path(name, base)
    path.unlink(missing_ok=True)


def list_metadata(base: Path | None = None) -> list[SandboxMetadata]:
    d = _metadata_dir(base)
    results: list[SandboxMetadata] = []
    for f in sorted(d.glob("*.json")):
        try:
            results.append(
                SandboxMetadata.model_validate_json(f.read_text(encoding="utf-8"))
            )
        except Exception:
            continue
    return results


def touch_activity(name: str, base: Path | None = None) -> None:
    """Update last_activity to now."""
    try:
        meta = load_metadata(name, base)
        meta.last_activity = datetime.now()
        save_metadata(meta, base)
    except FileNotFoundError:
        pass
