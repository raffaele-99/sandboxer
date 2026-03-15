"""Agent profile CRUD — YAML on disk, secrets via keyring."""
from __future__ import annotations

from pathlib import Path

import yaml

from .config import agents_dir
from .models import AgentProfile


def _agents_path(base: Path | None = None) -> Path:
    d = agents_dir(base)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _yaml_path(name: str, base: Path | None = None) -> Path:
    return _agents_path(base) / f"{name}.yml"


# -- CRUD --------------------------------------------------------------------

def save_agent(profile: AgentProfile, base: Path | None = None) -> Path:
    path = _yaml_path(profile.name, base)
    data = profile.model_dump()
    # Never serialise the raw key — it should come from keyring or env at runtime.
    data.pop("api_key_env_var", None)
    data["api_key_env_var"] = profile.api_key_env_var
    path.write_text(
        yaml.dump(data, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def load_agent(name: str, base: Path | None = None) -> AgentProfile:
    path = _yaml_path(name, base)
    if not path.exists():
        raise FileNotFoundError(f"agent profile not found: {name}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgentProfile(**data)


def delete_agent(name: str, base: Path | None = None) -> None:
    _yaml_path(name, base).unlink(missing_ok=True)


def list_agents(base: Path | None = None) -> list[AgentProfile]:
    d = _agents_path(base)
    profiles: list[AgentProfile] = []
    for yml in sorted(d.glob("*.yml")):
        try:
            profiles.append(load_agent(yml.stem, base))
        except Exception:
            continue
    return profiles
