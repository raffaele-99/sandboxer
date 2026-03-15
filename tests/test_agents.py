"""Tests for sandboxer.core.agents."""
from __future__ import annotations

from pathlib import Path

import pytest

from sandboxer.core.agents import (
    delete_agent,
    list_agents,
    load_agent,
    save_agent,
)
from sandboxer.core.models import AgentProfile


class TestAgentCRUD:
    def test_save_and_load(self, tmp_path: Path) -> None:
        profile = AgentProfile(
            name="claude-work",
            agent_type="claude",
            api_key_env_var="ANTHROPIC_API_KEY",
            auth_dir="/home/user/.claude",
            default_args=["--dangerously-skip-permissions"],
        )
        save_agent(profile, base=tmp_path)

        loaded = load_agent("claude-work", base=tmp_path)
        assert loaded.name == "claude-work"
        assert loaded.agent_type == "claude"
        assert loaded.api_key_env_var == "ANTHROPIC_API_KEY"
        assert loaded.auth_dir == "/home/user/.claude"
        assert loaded.default_args == ["--dangerously-skip-permissions"]

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="agent profile not found"):
            load_agent("nope", base=tmp_path)

    def test_delete(self, tmp_path: Path) -> None:
        profile = AgentProfile(name="temp", agent_type="codex")
        save_agent(profile, base=tmp_path)
        assert (tmp_path / "agents" / "temp.yml").exists()

        delete_agent("temp", base=tmp_path)
        assert not (tmp_path / "agents" / "temp.yml").exists()

    def test_list_agents(self, tmp_path: Path) -> None:
        for name in ["alice", "bob"]:
            save_agent(
                AgentProfile(name=name, agent_type="claude"),
                base=tmp_path,
            )

        result = list_agents(base=tmp_path)
        names = [a.name for a in result]
        assert names == ["alice", "bob"]

    def test_list_empty(self, tmp_path: Path) -> None:
        result = list_agents(base=tmp_path)
        assert result == []
