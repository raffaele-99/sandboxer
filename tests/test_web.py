"""Tests for the sandboxer web UI module."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from sandboxer.core.models import SandboxInfo
from sandboxer.web import create_app
from sandboxer.web.auth import TokenAuthMiddleware
from sandboxer.web.terminal import SessionManager, TerminalSession

TOKEN = "test-token-abc123"


@pytest.fixture
def app():
    return create_app(token=TOKEN)


@pytest.fixture
def client(app):
    return TestClient(app)


# -- Auth middleware ---------------------------------------------------------

class TestAuth:
    def test_unauthenticated_returns_401(self, client):
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 401

    def test_bearer_token_authenticates(self, client):
        with patch("sandboxer.web.routes.dashboard.list_running_sandboxes", return_value=[]):
            resp = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200

    def test_query_param_authenticates_and_sets_cookie(self, client):
        with patch("sandboxer.web.routes.dashboard.list_running_sandboxes", return_value=[]):
            resp = client.get(f"/?token={TOKEN}")
        assert resp.status_code == 200
        assert "sandboxer_token" in resp.cookies

    def test_cookie_authenticates(self, client):
        client.cookies.set("sandboxer_token", TOKEN)
        with patch("sandboxer.web.routes.dashboard.list_running_sandboxes", return_value=[]):
            resp = client.get("/")
        assert resp.status_code == 200

    def test_wrong_token_returns_401(self, client):
        resp = client.get("/?token=wrong")
        assert resp.status_code == 401

    def test_static_files_exempt_from_auth(self, client):
        resp = client.get("/static/style.css")
        assert resp.status_code == 200


# -- Dashboard route ---------------------------------------------------------

class TestDashboard:
    def test_dashboard_renders_sandbox_list(self, client):
        sandboxes = [
            SandboxInfo(name="sandboxer-test-1", status="running"),
            SandboxInfo(name="sandboxer-test-2", status="stopped"),
        ]
        with patch("sandboxer.web.routes.dashboard.list_running_sandboxes", return_value=sandboxes):
            resp = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        assert "sandboxer-test-1" in resp.text
        assert "sandboxer-test-2" in resp.text

    def test_dashboard_empty(self, client):
        with patch("sandboxer.web.routes.dashboard.list_running_sandboxes", return_value=[]):
            resp = client.get("/", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        assert "No sandboxes running" in resp.text


# -- Sandbox CRUD partials --------------------------------------------------

class TestSandboxRoutes:
    def test_sandbox_list_partial(self, client):
        sandboxes = [SandboxInfo(name="sandboxer-foo", status="running")]
        with patch("sandboxer.web.routes.sandboxes.list_running_sandboxes", return_value=sandboxes):
            resp = client.get("/sandboxes", headers={"Authorization": f"Bearer {TOKEN}"})
        assert resp.status_code == 200
        assert "sandboxer-foo" in resp.text

    def test_sandbox_stop(self, client):
        with (
            patch("sandboxer.web.routes.sandboxes.stop_sandbox") as mock_stop,
            patch("sandboxer.web.routes.sandboxes.list_running_sandboxes", return_value=[]),
        ):
            resp = client.post(
                "/sandboxes/sandboxer-test/stop",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        assert resp.status_code == 200
        mock_stop.assert_called_once_with("sandboxer-test")

    def test_sandbox_remove(self, client):
        with (
            patch("sandboxer.web.routes.sandboxes.remove_sandbox") as mock_rm,
            patch("sandboxer.web.routes.sandboxes.list_running_sandboxes", return_value=[]),
        ):
            resp = client.request(
                "DELETE",
                "/sandboxes/sandboxer-test/rm",
                headers={"Authorization": f"Bearer {TOKEN}"},
            )
        assert resp.status_code == 200
        mock_rm.assert_called_once_with("sandboxer-test")


# -- Terminal page -----------------------------------------------------------

class TestTerminalPage:
    def test_terminal_page_renders(self, client):
        resp = client.get(
            "/terminal/sandboxer-test",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert resp.status_code == 200
        assert "xterm" in resp.text
        assert "sandboxer-test" in resp.text


# -- Session manager ---------------------------------------------------------

class TestSessionManager:
    def test_create_and_get(self):
        mgr = SessionManager()
        with patch.object(TerminalSession, "start"):
            session = mgr.create("id1", "sandbox1")
        assert mgr.get("id1") is session

    def test_create_idempotent(self):
        mgr = SessionManager()
        with patch.object(TerminalSession, "start"):
            s1 = mgr.create("id1", "sandbox1")
            s2 = mgr.create("id1", "sandbox1")
        assert s1 is s2

    @pytest.mark.asyncio
    async def test_close(self):
        mgr = SessionManager()
        with patch.object(TerminalSession, "start"):
            mgr.create("id1", "sandbox1")
        with patch.object(TerminalSession, "close", new_callable=AsyncMock):
            await mgr.close("id1")
        assert mgr.get("id1") is None

    @pytest.mark.asyncio
    async def test_close_all(self):
        mgr = SessionManager()
        with patch.object(TerminalSession, "start"):
            mgr.create("id1", "sandbox1")
            mgr.create("id2", "sandbox2")
        with patch.object(TerminalSession, "close", new_callable=AsyncMock):
            await mgr.close_all()
        assert mgr.get("id1") is None
        assert mgr.get("id2") is None
