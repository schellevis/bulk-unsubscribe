"""FastAPI application entry point."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import accounts, scan, senders

# Create all database tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Bulk Unsubscribe",
    description="Mobile-first tool to help you unsubscribe from newsletters.",
    version="0.1.0",
)

# API routes
app.include_router(accounts.router)
app.include_router(senders.router)
app.include_router(scan.router)

# Serve the frontend SPA
static_dir = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/", include_in_schema=False)
def serve_frontend():
    return FileResponse(str(static_dir / "index.html"))
