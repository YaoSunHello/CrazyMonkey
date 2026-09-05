import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.routing import Match, Mount

from .relay.api import router as relay_router
from .runtime.api import router as runtime_router
from .runtime.beacon import router as beacon_router
from .pack_api import router as pack_router

app = FastAPI(title="CrazyMonkey API")

cors_origins = [
    item.strip()
    for item in os.getenv(
        "CRAZYMONKEY_CORS_ORIGINS",
        "http://localhost:4173,http://127.0.0.1:4173,http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if item.strip()
]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "If-None-Match"],
        expose_headers=["Content-Disposition", "ETag", "X-Review-Version", "X-Snapshot-SHA256"],
    )

app.include_router(relay_router)
app.include_router(runtime_router)
app.include_router(beacon_router)
app.include_router(pack_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


class _BackendAwareStaticMount(Mount):
    """Leave known backend paths to their routes, including method errors."""

    def __init__(self, path, *, app, backend_routes, name):
        super().__init__(path, app=app, name=name)
        self.backend_routes = tuple(backend_routes)

    def matches(self, scope):
        if any(route.matches(scope)[0] == Match.PARTIAL for route in self.backend_routes):
            return Match.NONE, {}
        return super().matches(scope)


frontend_build = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_build.is_dir():
    app.router.routes.append(_BackendAwareStaticMount(
        "/", app=StaticFiles(directory=frontend_build, html=True),
        backend_routes=app.router.routes, name="desktop-ui",
    ))
