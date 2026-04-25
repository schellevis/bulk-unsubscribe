import hashlib
import hmac

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
