from fastapi import FastAPI

app = FastAPI(title="Bulk Unsubscribe", version="0.2.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
