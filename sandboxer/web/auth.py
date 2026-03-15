"""Token-based authentication middleware for the web UI."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response


class TokenAuthMiddleware(BaseHTTPMiddleware):
    """Authenticate via bearer token, cookie, or query parameter.

    On first successful auth via ``?token=``, sets an HttpOnly cookie so
    subsequent requests don't need the query param.
    """

    COOKIE_NAME = "sandboxer_token"
    EXEMPT_PREFIXES = ("/static/",)

    def __init__(self, app, *, token: str) -> None:  # noqa: ANN001
        super().__init__(app)
        self.token = token

    async def dispatch(self, request: Request, call_next) -> Response:  # noqa: ANN001
        path = request.url.path

        # Static files don't need auth.
        for prefix in self.EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Try bearer header.
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer ") and auth_header[7:] == self.token:
            return await call_next(request)

        # Try cookie.
        cookie = request.cookies.get(self.COOKIE_NAME)
        if cookie == self.token:
            return await call_next(request)

        # Try query param — set cookie on success.
        query_token = request.query_params.get("token")
        if query_token == self.token:
            response = await call_next(request)
            response.set_cookie(
                self.COOKIE_NAME,
                self.token,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,  # 7 days
            )
            return response

        return PlainTextResponse("Unauthorized", status_code=401)
