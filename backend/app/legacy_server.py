"""Isolated original V0 server: uvicorn app.legacy_server:app --app-dir backend.

Run in its own process with one worker. Original routers use module-level service
references; the lifespan temporarily binds them to this server's isolated stores.
No PackService or Turbo Audit routes are imported or registered here.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
import os
from pathlib import Path
import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .legacy_model import create_analyst
from .relay import api as relay_api
from .relay.email_delivery import EmailDeliveryService
from .relay.export_service import ExportService
from .runtime import api as runtime_api
from .runtime import beacon
from .runtime import service as runtime_service


_REPOSITORY = Path(__file__).resolve().parents[2]
_BINDING_LOCK = threading.Lock()


def create_app(mode: str | None = None, output_dir: Path | None = None) -> FastAPI:
    selected_mode = mode if mode is not None else os.environ.get('CRAZYMONKEY_LEGACY_MODE', 'OFFLINE')
    if selected_mode not in {'OFFLINE', 'LIVE_MODEL'}:
        raise ValueError('CRAZYMONKEY_LEGACY_MODE must be OFFLINE or LIVE_MODEL.')
    selected_output = Path(output_dir) if output_dir is not None else Path(
        os.environ.get('CRAZYMONKEY_RELAY_OUTPUT_DIR', _REPOSITORY / 'outputs' / 'legacy-server'))
    selected_output = selected_output.resolve()

    @asynccontextmanager
    async def lifespan(application):
        if not _BINDING_LOCK.acquire(blocking=False):
            raise RuntimeError('Original V0 server must run in its own single-worker process.')
        handle = None
        previous = None
        try:
            handle = create_analyst(selected_mode)
            exports = ExportService(selected_output, _REPOSITORY / 'backend/app/schemas/review_export.schema.json')
            reviews = runtime_service.ReviewService(export_service=exports, analyst=handle.analyst)
            delivery = EmailDeliveryService.from_environment(selected_output / 'email/send-log.jsonl')
            previous = (relay_api.service, relay_api.delivery, runtime_api.reviews, runtime_service.reviews)
            relay_api.service, relay_api.delivery = exports, delivery
            runtime_api.reviews = runtime_service.reviews = reviews
            application.state.legacy_handle = handle
            application.state.legacy_reviews = reviews
            application.state.legacy_exports = exports
            yield
        finally:
            if previous is not None:
                relay_api.service, relay_api.delivery, runtime_api.reviews, runtime_service.reviews = previous
            if handle is not None:
                handle.close()
            _BINDING_LOCK.release()

    application = FastAPI(title='CrazyMonkey Original V0 API', lifespan=lifespan)
    application.state.legacy_mode = selected_mode
    application.state.legacy_output_directory = selected_output
    application.add_middleware(
        CORSMiddleware,
        allow_origins=['http://localhost:4174', 'http://127.0.0.1:4174'],
        allow_credentials=False, allow_methods=['GET', 'POST', 'PATCH', 'OPTIONS'],
        allow_headers=['Content-Type', 'If-None-Match'],
        expose_headers=['Content-Disposition', 'ETag', 'X-Review-Version', 'X-Snapshot-SHA256'],
    )
    application.include_router(relay_api.router)
    application.include_router(runtime_api.router)
    application.include_router(beacon.router)

    @application.get('/health')
    def health():
        return {'status': 'ok', 'layer': 'ORIGINAL_V0'}

    @application.get('/api/legacy/status')
    def legacy_status():
        handle = getattr(application.state, 'legacy_handle', None)
        if handle is None:
            return {'layer': 'ORIGINAL_V0', 'status': 'NOT_STARTED', 'mode': selected_mode,
                    'model_call_count': 0, 'request_count': 0, 'error_count': 0}
        return {'layer': 'ORIGINAL_V0', 'status': 'CLOSED' if handle.status()['closed'] else 'READY',
                **handle.status()}

    return application


app = create_app()
