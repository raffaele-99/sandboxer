"""Tests for sandboxer.core.credential_proxy."""
from __future__ import annotations

import os
from unittest.mock import patch

from sandboxer.core.credential_proxy import (
    KNOWN_ENDPOINTS,
    CredentialProxy,
    build_credentials,
)
from sandboxer.core.models import AgentProfile


class TestKnownEndpoints:
    def test_anthropic_endpoint(self) -> None:
        assert "api.anthropic.com" in KNOWN_ENDPOINTS
        assert KNOWN_ENDPOINTS["api.anthropic.com"] == "x-api-key"

    def test_openai_endpoint(self) -> None:
        assert "api.openai.com" in KNOWN_ENDPOINTS
        assert KNOWN_ENDPOINTS["api.openai.com"] == "Authorization"

    def test_google_endpoint(self) -> None:
        assert "generativelanguage.googleapis.com" in KNOWN_ENDPOINTS


class TestCredentialProxy:
    def test_init_defaults(self) -> None:
        proxy = CredentialProxy(credentials={})
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 9876
        assert proxy.address == "http://127.0.0.1:9876"

    def test_init_custom(self) -> None:
        proxy = CredentialProxy(
            credentials={"api.openai.com": "sk-test"},
            host="0.0.0.0",
            port=8080,
        )
        assert proxy.address == "http://0.0.0.0:8080"
        assert proxy.credentials["api.openai.com"] == "sk-test"


class TestBuildCredentials:
    def test_from_env_vars(self) -> None:
        agents = [
            AgentProfile(
                name="claude",
                agent_type="claude",
                api_key_env_var="ANTHROPIC_API_KEY",
            ),
            AgentProfile(
                name="codex",
                agent_type="codex",
                api_key_env_var="OPENAI_API_KEY",
            ),
        ]
        env = {
            "ANTHROPIC_API_KEY": "sk-ant-test",
            "OPENAI_API_KEY": "sk-oai-test",
        }
        with patch.dict(os.environ, env, clear=False):
            creds = build_credentials(agents)
        assert creds["api.anthropic.com"] == "sk-ant-test"
        assert creds["api.openai.com"] == "sk-oai-test"

    def test_missing_env_var(self) -> None:
        agents = [
            AgentProfile(
                name="claude",
                agent_type="claude",
                api_key_env_var="ANTHROPIC_API_KEY",
            ),
        ]
        with patch.dict(os.environ, {}, clear=True):
            creds = build_credentials(agents)
        assert creds == {}

    def test_empty_env_var_name(self) -> None:
        agents = [AgentProfile(name="test", agent_type="claude", api_key_env_var="")]
        creds = build_credentials(agents)
        assert creds == {}
