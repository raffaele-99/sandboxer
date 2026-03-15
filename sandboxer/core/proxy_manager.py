"""Sync-to-async bridge for the credential proxy."""
from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field

from .credential_proxy import CredentialProxy, build_credentials
from .models import AgentProfile


@dataclass
class ProxyHandle:
    proxy: CredentialProxy
    url: str


class ProxyManager:
    """Manages credential proxy lifecycle from synchronous code."""

    def __init__(self) -> None:
        self._proxies: dict[str, ProxyHandle] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._next_port_offset = 0
        self._lock = threading.Lock()

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or not self._loop.is_running():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, daemon=True
                )
                self._thread.start()
            return self._loop

    def start_proxy(
        self,
        sandbox_name: str,
        agents: list[AgentProfile],
        *,
        host: str = "127.0.0.1",
        port: int = 9876,
    ) -> str:
        """Start a credential proxy for *sandbox_name*. Returns the proxy URL."""
        loop = self._ensure_loop()
        actual_port = port + self._next_port_offset
        self._next_port_offset += 1

        creds = build_credentials(agents)
        proxy = CredentialProxy(creds, host=host, port=actual_port)

        future = asyncio.run_coroutine_threadsafe(proxy.start(), loop)
        future.result(timeout=10)

        url = proxy.address
        self._proxies[sandbox_name] = ProxyHandle(proxy=proxy, url=url)
        return url

    def stop_proxy(self, sandbox_name: str) -> None:
        """Stop the credential proxy for *sandbox_name*."""
        handle = self._proxies.pop(sandbox_name, None)
        if handle is None:
            return
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(handle.proxy.stop(), loop)
        future.result(timeout=10)

    def get_proxy_url(self, sandbox_name: str) -> str | None:
        handle = self._proxies.get(sandbox_name)
        return handle.url if handle else None

    def stop_all(self) -> None:
        """Stop all proxies and shut down the event loop."""
        for name in list(self._proxies):
            self.stop_proxy(name)
        with self._lock:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread is not None:
                    self._thread.join(timeout=5)
                self._loop = None
                self._thread = None


_manager: ProxyManager | None = None
_manager_lock = threading.Lock()


def get_proxy_manager() -> ProxyManager:
    """Return (or create) the singleton ProxyManager."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ProxyManager()
        return _manager
