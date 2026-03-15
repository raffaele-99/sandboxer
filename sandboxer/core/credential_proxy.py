"""Host-side HTTP proxy that injects API credentials into outbound requests.

Sandboxes never see real API keys — they only know the proxy URL.  The proxy
intercepts requests to known AI API endpoints and injects the appropriate
``Authorization`` header from the agent profile.
"""
from __future__ import annotations

import asyncio
import sys
from http import HTTPStatus
from typing import Any

from .models import AgentProfile

# Endpoint patterns → header injection rules.
KNOWN_ENDPOINTS: dict[str, str] = {
    "api.anthropic.com": "x-api-key",
    "api.openai.com": "Authorization",
    "generativelanguage.googleapis.com": "x-goog-api-key",
}


class CredentialProxy:
    """A simple TCP-based forward proxy that injects credentials.

    Uses ``asyncio`` streams so it can be started/stopped alongside the
    main application without blocking.
    """

    def __init__(
        self,
        credentials: dict[str, str],
        *,
        host: str = "127.0.0.1",
        port: int = 9876,
    ) -> None:
        self.credentials = credentials  # {endpoint_host: api_key_value}
        self.host = host
        self.port = port
        self._server: asyncio.AbstractServer | None = None

    async def _handle_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle a single CONNECT-style proxy request."""
        try:
            request_line = await asyncio.wait_for(reader.readline(), timeout=10)
            if not request_line:
                writer.close()
                return
            line = request_line.decode("utf-8", errors="replace").strip()

            # Read remaining headers.
            headers: list[str] = []
            while True:
                h = await asyncio.wait_for(reader.readline(), timeout=10)
                h_str = h.decode("utf-8", errors="replace").strip()
                if not h_str:
                    break
                headers.append(h_str)

            # Extract host from the request or Host header.
            target_host = ""
            for h in headers:
                if h.lower().startswith("host:"):
                    target_host = h.split(":", 1)[1].strip().split(":")[0]
                    break

            # Inject credentials if the target is a known AI endpoint.
            injected_headers: list[str] = []
            if target_host in KNOWN_ENDPOINTS:
                header_name = KNOWN_ENDPOINTS[target_host]
                api_key = self.credentials.get(target_host, "")
                if api_key:
                    if header_name.lower() == "authorization":
                        injected_headers.append(f"Authorization: Bearer {api_key}")
                    else:
                        injected_headers.append(f"{header_name}: {api_key}")

            # Forward to target (simplified — production would use full HTTP proxy).
            port = 443 if "https" in line.lower() or ":443" in line else 80
            try:
                remote_reader, remote_writer = await asyncio.open_connection(
                    target_host, port
                )
            except Exception:
                error = f"HTTP/1.1 {HTTPStatus.BAD_GATEWAY.value} Bad Gateway\r\n\r\n"
                writer.write(error.encode())
                await writer.drain()
                writer.close()
                return

            # Rebuild the request with injected headers.
            rebuilt = line + "\r\n"
            for h in headers:
                # Skip any existing auth headers we're overriding.
                h_lower = h.lower()
                skip = any(
                    h_lower.startswith(ih.split(":")[0].lower() + ":")
                    for ih in injected_headers
                )
                if not skip:
                    rebuilt += h + "\r\n"
            for ih in injected_headers:
                rebuilt += ih + "\r\n"
            rebuilt += "\r\n"

            remote_writer.write(rebuilt.encode())
            await remote_writer.drain()

            # Pipe data bidirectionally.
            await asyncio.gather(
                self._pipe(reader, remote_writer),
                self._pipe(remote_reader, writer),
                return_exceptions=True,
            )
        except Exception:
            pass
        finally:
            writer.close()

    @staticmethod
    async def _pipe(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            while True:
                data = await reader.read(8192)
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()

    async def start(self) -> None:
        self._server = await asyncio.start_server(
            self._handle_connect,
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"


def build_credentials(agents: list[AgentProfile]) -> dict[str, str]:
    """Build a credentials dict from agent profiles by resolving env vars."""
    import os

    creds: dict[str, str] = {}
    env_to_endpoint = {
        "ANTHROPIC_API_KEY": "api.anthropic.com",
        "OPENAI_API_KEY": "api.openai.com",
        "GOOGLE_API_KEY": "generativelanguage.googleapis.com",
    }
    for agent in agents:
        if agent.api_key_env_var:
            value = os.environ.get(agent.api_key_env_var, "")
            if value:
                endpoint = env_to_endpoint.get(agent.api_key_env_var)
                if endpoint:
                    creds[endpoint] = value
    return creds
