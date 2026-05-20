"""Per-request context (currently: client IP).

A `ContextVar` populated by the `ClientIPMiddleware` so that any code path
inside a request (in particular `audit_log.log_event`) can read the caller's
IP without every router having to thread a `Request` object through its
signature. Trusts the first hop of `X-Forwarded-For` when a reverse proxy
sets it, otherwise falls back to the direct peer address.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_client_ip_ctx: ContextVar[Optional[str]] = ContextVar("client_ip", default=None)


def current_client_ip() -> Optional[str]:
    """Return the IP for the in-flight request, or None outside a request."""
    return _client_ip_ctx.get()


def extract_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


class ClientIPMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = _client_ip_ctx.set(extract_ip(request) or None)
        try:
            return await call_next(request)
        finally:
            _client_ip_ctx.reset(token)
