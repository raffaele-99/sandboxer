"""Tests for sandboxer.core.proxy_manager."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from sandboxer.core.models import AgentProfile
from sandboxer.core.proxy_manager import ProxyManager


class TestProxyManager:
    def test_start_and_stop_proxy(self) -> None:
        pm = ProxyManager()
        agent = AgentProfile(
            name="test-agent",
            agent_type="claude",
            api_key_env_var="ANTHROPIC_API_KEY",
        )

        with patch("sandboxer.core.proxy_manager.CredentialProxy") as MockProxy:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.address = "http://127.0.0.1:9876"
            MockProxy.return_value = mock_instance

            url = pm.start_proxy("sandbox-1", [agent], port=9876)
            assert url == "http://127.0.0.1:9876"
            assert pm.get_proxy_url("sandbox-1") == "http://127.0.0.1:9876"

            pm.stop_proxy("sandbox-1")
            assert pm.get_proxy_url("sandbox-1") is None

        pm.stop_all()

    def test_stop_nonexistent_is_noop(self) -> None:
        pm = ProxyManager()
        pm.stop_proxy("nonexistent")  # Should not raise.
        pm.stop_all()

    def test_port_increments(self) -> None:
        pm = ProxyManager()
        agent = AgentProfile(name="a", agent_type="claude")

        with patch("sandboxer.core.proxy_manager.CredentialProxy") as MockProxy:
            mock_instance = MagicMock()
            mock_instance.start = AsyncMock()
            mock_instance.stop = AsyncMock()
            mock_instance.address = "http://127.0.0.1:9876"
            MockProxy.return_value = mock_instance

            pm.start_proxy("s1", [agent], port=9876)
            pm.start_proxy("s2", [agent], port=9876)

            # Second call should use port 9877.
            calls = MockProxy.call_args_list
            assert calls[0][1]["port"] == 9876
            assert calls[1][1]["port"] == 9877

        pm.stop_all()

    def test_get_proxy_url_returns_none_for_unknown(self) -> None:
        pm = ProxyManager()
        assert pm.get_proxy_url("nope") is None
        pm.stop_all()
