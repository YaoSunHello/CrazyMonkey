"""The combined CrazyMonkey HTTP surface.

The original profile endpoints remain a thin view over the JSON-on-disk track
definitions. BEACON's review routes are mounted alongside them so the browser
can send original files through ATLAS, the verified runtime, and RELAY without
changing the existing CLI pipeline.
"""

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.profiles import load, load_all
from app.relay.api import router as relay_router
from app.runtime.api import router as runtime_router
from app.runtime.beacon import router as beacon_router
from app.ui_bridge import router as ui_bridge_router

app = FastAPI(title="CrazyMonkey API")

cors_origins = [
    item.strip()
    for item in os.getenv(
        "CRAZYMONKEY_CORS_ORIGINS",
        "http://localhost:4173,http://127.0.0.1:4173,"
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "If-None-Match", "Idempotency-Key"],
        expose_headers=[
            "Content-Disposition",
            "ETag",
            "X-Review-Version",
            "X-Snapshot-SHA256",
        ],
    )

app.include_router(relay_router)
app.include_router(runtime_router)
app.include_router(beacon_router)
app.include_router(ui_bridge_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/profiles")
def profiles() -> list[dict]:
    """Every track, as a picker needs it: identity and shape, not the prompts."""
    return [p.summary() for p in load_all()]


@app.get("/api/profiles/{profile_id}")
def profile(profile_id: str) -> dict:
    try:
        return load(profile_id).summary()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # A malformed profile is a server-side fault, not a bad request — the
        # caller asked for something that exists and we cannot serve it.
        raise HTTPException(status_code=500, detail=str(exc)) from exc
