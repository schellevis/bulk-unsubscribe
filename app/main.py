from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.auth import AuthMiddleware, check_password, session_secret
from app.config import get_settings
from app.jobs.runner import JobRunner

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR.parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    from app.services.crypto import CredentialCipher

    CredentialCipher.from_settings(settings)
    JobRunner.recover_orphans()
    yield


app = FastAPI(title="Bulk Unsubscribe", version="0.2.0", lifespan=lifespan)
app.add_middleware(AuthMiddleware)
app.add_middleware(
    SessionMiddleware, secret_key=session_secret(), max_age=60 * 60 * 24 * 30
)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from app.routes import accounts as accounts_routes  # noqa: E402
from app.routes import bulk_action as bulk_action_routes  # noqa: E402
from app.routes import jobs as jobs_routes  # noqa: E402
from app.routes import senders as senders_routes  # noqa: E402
from app.routes import unsubscribe as unsubscribe_routes  # noqa: E402
from app.routes import whitelist as whitelist_routes  # noqa: E402

app.include_router(accounts_routes.router)
app.include_router(jobs_routes.router)
app.include_router(senders_routes.router)
app.include_router(whitelist_routes.router)
app.include_router(bulk_action_routes.router)
app.include_router(unsubscribe_routes.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {"error": None, "next": request.query_params.get("next", "/")},
    )


@app.post("/login")
def login_submit(
    request: Request,
    password: str = Form(...),
    next: str = Form("/"),
):
    if check_password(password):
        request.session["authed"] = True
        return RedirectResponse(url=next or "/", status_code=303)
    return templates.TemplateResponse(
        request,
        "pages/login.html",
        {"error": "Wrong password", "next": next},
        status_code=401,
    )


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
