"""Tests for sandboxer.core.config."""
from __future__ import annotations

from pathlib import Path

from sandboxer.core.config import GlobalConfig


class TestGlobalConfig:
    def test_defaults(self) -> None:
        cfg = GlobalConfig()
        assert cfg.default_template is None
        assert cfg.default_agent is None
        assert cfg.credential_proxy_port == 9876
        assert cfg.auto_cleanup_orphans is True
        assert cfg.network_mode == "bridge"

    def test_save_and_load(self, tmp_path: Path) -> None:
        cfg = GlobalConfig(
            default_template="python-dev",
            default_agent="claude-work",
            credential_proxy_port=8888,
            auto_cleanup_orphans=False,
            network_mode="host",
        )
        config_file = tmp_path / "config.yml"
        cfg.save(config_file)
        assert config_file.exists()

        loaded = GlobalConfig.load(config_file)
        assert loaded.default_template == "python-dev"
        assert loaded.default_agent == "claude-work"
        assert loaded.credential_proxy_port == 8888
        assert loaded.auto_cleanup_orphans is False
        assert loaded.network_mode == "host"

    def test_load_missing_file(self, tmp_path: Path) -> None:
        cfg = GlobalConfig.load(tmp_path / "nonexistent.yml")
        assert cfg.default_template is None
        assert cfg.credential_proxy_port == 9876
