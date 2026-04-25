from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _request_origin(request: Request) -> str:
    host = request.headers.get("host") or request.url.netloc
    return f"{request.url.scheme}://{host}"


def _origin_from_referer(value: str) -> str | None:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


class OriginProtectionMiddleware(BaseHTTPMiddleware):
    """Reject browser unsafe-method requests from a different origin."""

    async def dispatch(self, request: Request, call_next):
        if request.method not in UNSAFE_METHODS:
            return await call_next(request)

        expected = _request_origin(request)
        origin = request.headers.get("origin")
        if origin is not None:
            if origin == expected:
                return await call_next(request)
            return PlainTextResponse("cross-origin request rejected", status_code=403)

        referer = request.headers.get("referer")
        if referer is not None and _origin_from_referer(referer) != expected:
            return PlainTextResponse("cross-origin request rejected", status_code=403)

        return await call_next(request)
