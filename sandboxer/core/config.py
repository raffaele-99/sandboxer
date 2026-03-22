"""Global configuration, paths, and defaults."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

CONFIG_DIR_NAME = "sandboxer"
DEFAULT_CONFIG_FILENAME = "config.yml"
MOUNT_ALLOWLIST_FILENAME = "mount-allowlist.json"
TEMPLATES_DIR = "templates"
AGENTS_DIR = "agents"

# Blocked host paths that should never be mounted into a sandbox.
BLOCKED_MOUNT_PATTERNS: list[str] = [
    ".ssh",
    ".aws",
    ".docker",
    ".gnupg",
    ".config/gcloud",
    ".azure",
    ".kube",
    "credentials.json",
    "id_rsa",
    "id_ed25519",
]

SANDBOX_NAME_PREFIX = "sandboxer-"


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / CONFIG_DIR_NAME
    return Path.home() / ".config" / CONFIG_DIR_NAME


@dataclass
class GlobalConfig:
    default_template: str | None = None
    default_agent: str | None = None
    credential_proxy_port: int = 9876
    auto_cleanup_orphans: bool = True
    network_mode: str = "bridge"
    container_runtime: str = "runsc"  # "runsc" for gVisor, "" for default
    container_backend: str = "auto"  # "auto", "docker", or "apple"
    dns_server: str | None = None  # e.g. "8.8.8.8" — useful when VPN breaks gateway DNS
    default_ttl_seconds: int | None = None
    default_idle_timeout_seconds: int | None = None

    def save(self, path: Path | None = None) -> None:
        path = path or (config_dir() / DEFAULT_CONFIG_FILENAME)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "default_template": self.default_template,
            "default_agent": self.default_agent,
            "credential_proxy_port": self.credential_proxy_port,
            "auto_cleanup_orphans": self.auto_cleanup_orphans,
            "network_mode": self.network_mode,
            "container_runtime": self.container_runtime,
            "container_backend": self.container_backend,
            "dns_server": self.dns_server,
            "default_ttl_seconds": self.default_ttl_seconds,
            "default_idle_timeout_seconds": self.default_idle_timeout_seconds,
        }
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | None = None) -> GlobalConfig:
        path = path or (config_dir() / DEFAULT_CONFIG_FILENAME)
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            default_template=data.get("default_template"),
            default_agent=data.get("default_agent"),
            credential_proxy_port=data.get("credential_proxy_port", 9876),
            auto_cleanup_orphans=data.get("auto_cleanup_orphans", True),
            network_mode=data.get("network_mode", "bridge"),
            container_runtime=data.get("container_runtime", "runsc"),
            container_backend=data.get("container_backend", "auto"),
            dns_server=data.get("dns_server"),
            default_ttl_seconds=data.get("default_ttl_seconds"),
            default_idle_timeout_seconds=data.get("default_idle_timeout_seconds"),
        )


def templates_dir(base: Path | None = None) -> Path:
    return (base or config_dir()) / TEMPLATES_DIR


def agents_dir(base: Path | None = None) -> Path:
    return (base or config_dir()) / AGENTS_DIR
