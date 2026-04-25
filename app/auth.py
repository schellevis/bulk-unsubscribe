import hashlib
import hmac
from urllib.parse import urlparse

from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings


def session_secret() -> str:
    return hashlib.sha256(get_settings().fernet_key.encode()).hexdigest()


class AuthMiddleware(BaseHTTPMiddleware):
    PUBLIC = {"/login", "/healthz"}

    async def dispatch(self, request: Request, call_next):
        if get_settings().auth_password is None:
            return await call_next(request)
        path = request.url.path
        if path in self.PUBLIC or path.startswith("/static/"):
            return await call_next(request)
        if request.session.get("authed") is True:
            return await call_next(request)
        return RedirectResponse(url=f"/login?next={path}", status_code=303)


def check_password(submitted: str) -> bool:
    expected = get_settings().auth_password or ""
    if not expected:
        return False
    return hmac.compare_digest(submitted, expected)


def safe_next(next_url: str | None) -> str:
    """Return *next_url* only when it is a safe same-origin relative path.

    A safe path must start with exactly one ``/``, must not be a
    protocol-relative URL (``//host``), and must not carry a scheme or
    authority (detected via :func:`urllib.parse.urlparse`).
    Any value that fails these checks falls back to ``/``.
    """
    if not next_url:
        return "/"
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        return "/"
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url
