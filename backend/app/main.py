import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

from . import assignments_api, auth_api, courses_api, portal_api, simulation_api
from .config import ROOT, Settings
from .db import make_engine, make_sessions
from .middleware import RequestBoundary
from .protection import StagingProtection
from .security import AuthRateLimit
from .telemetry import TelemetrySender


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    engine = make_engine(settings.sqlite_path)
    telemetry = None
    if settings.telemetry_collector_url:
        telemetry = TelemetrySender(settings.telemetry_collector_url, settings.telemetry_app_id,
                                    bytes.fromhex(settings.telemetry_hmac_key.get_secret_value()))
    protection = StagingProtection(settings) if settings.protection_url else None

    @asynccontextmanager
    async def lifespan(_app):
        workers = [asyncio.create_task(service.run()) for service in (telemetry, protection) if service]
        try:
            yield
        finally:
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            engine.dispose()

    development = settings.app_env != "production"
    app = FastAPI(title="Northfield Student Portal", lifespan=lifespan,
                  docs_url="/docs" if development else None,
                  redoc_url=None, openapi_url="/openapi.json" if development else None)
    app.state.settings = settings
    app.state.sessions = make_sessions(engine)
    app.state.auth_limit = AuthRateLimit(settings.auth_requests_per_minute)
    app.state.protection = protection
    app.state.subject_key = bytes.fromhex(settings.protection_subject_key.get_secret_value())
    api_prefix = "/api"
    api_routers = (auth_api.router, courses_api.router, assignments_api.router, portal_api.router, simulation_api.router)
    route_templates = frozenset(api_prefix + route.path_format for router in api_routers
                                for route in router.routes if isinstance(route, APIRoute))
    app.add_middleware(RequestBoundary, settings=settings, telemetry=telemetry,
                       api_prefix=api_prefix, route_templates=route_templates)
    app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "DELETE"],
                       allow_headers=["Content-Type", "X-CSRF-Token", "X-CyberShield-Key", "Authorization"],
                       expose_headers=["X-Request-ID"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        request.state.validation_outcome = "denied"
        # Pydantic's error input and context can include passwords or submitted text.
        credential = request.url.path == "/api/auth/login"
        details = [dict(field=str(error["loc"][-1]), message=error["msg"])
                   for error in exc.errors() if error["type"] != "extra_forbidden"]
        return JSONResponse({"detail": "Invalid email or password" if credential else "Check the highlighted fields",
                             "errors": [] if credential else details}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(_request: Request, _error: SQLAlchemyError):
        return JSONResponse({"detail": "The data service is temporarily unavailable"}, status_code=503)

    @app.get("/health", tags=["Health"])
    def health():
        with engine.connect() as connection:
            connection.execute(text("SELECT 1 FROM users LIMIT 1"))
        return {"status": "ok"}

    for router in api_routers:
        app.include_router(router, prefix=api_prefix)

    dist = ROOT / "frontend" / "dist"
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def frontend(path: str):
            if path == "api" or path.startswith("api/") or path.startswith("."):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})

    return app
