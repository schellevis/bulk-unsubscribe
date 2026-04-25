from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

from app.routes import accounts as accounts_routes  # noqa: E402
from app.routes import jobs as jobs_routes  # noqa: E402
from app.routes import senders as senders_routes  # noqa: E402
from app.routes import whitelist as whitelist_routes  # noqa: E402

app.include_router(accounts_routes.router)
app.include_router(jobs_routes.router)
app.include_router(senders_routes.router)
app.include_router(whitelist_routes.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
