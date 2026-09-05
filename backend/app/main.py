import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .relay.api import router as relay_router

app = FastAPI(title="CrazyMonkey API")

cors_origins = [
    item.strip()
    for item in os.getenv(
        "CRAZYMONKEY_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "If-None-Match"],
        expose_headers=["Content-Disposition", "ETag", "X-Review-Version", "X-Snapshot-SHA256"],
    )

app.include_router(relay_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
