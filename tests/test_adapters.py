"""Tests for sandboxer.core.adapters."""
from __future__ import annotations

from sandboxer.core.adapters import (
    ADAPTERS,
    adapter_dockerfile_lines,
    get_adapter,
)


class TestAdapterRegistry:
    def test_claude_adapter_exists(self) -> None:
        adapter = get_adapter("claude")
        assert adapter is not None
        assert adapter.name == "claude"
        assert adapter.cli_binary == "claude"

    def test_codex_adapter_exists(self) -> None:
        adapter = get_adapter("codex")
        assert adapter is not None
        assert adapter.name == "codex"
        assert adapter.cli_binary == "codex"

    def test_gemini_adapter_exists(self) -> None:
        adapter = get_adapter("gemini")
        assert adapter is not None
        assert adapter.name == "gemini"

    def test_unknown_adapter_returns_none(self) -> None:
        assert get_adapter("unknown") is None

    def test_all_adapters_registered(self) -> None:
        assert set(ADAPTERS.keys()) == {"claude", "codex", "gemini"}


class TestAdapterDockerfileLines:
    def test_claude_lines(self) -> None:
        lines = adapter_dockerfile_lines("claude")
        assert len(lines) >= 2
        assert any("apt-get" in l for l in lines)
        assert any("npm install -g" in l and "claude-code" in l for l in lines)

    def test_codex_lines(self) -> None:
        lines = adapter_dockerfile_lines("codex")
        assert len(lines) >= 2
        assert any("apt-get" in l for l in lines)
        assert any("codex" in l.lower() for l in lines)

    def test_gemini_lines(self) -> None:
        lines = adapter_dockerfile_lines("gemini")
        assert len(lines) >= 2
        assert any("npm install -g" in l and "gemini" in l for l in lines)

    def test_unknown_returns_empty(self) -> None:
        assert adapter_dockerfile_lines("unknown") == []

    def test_adapters_are_frozen(self) -> None:
        adapter = get_adapter("claude")
        assert adapter is not None
        import pytest
        with pytest.raises(AttributeError):
            adapter.name = "modified"  # type: ignore[misc]
