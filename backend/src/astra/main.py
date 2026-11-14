import csv
import logging
import sqlite3
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from astra.config import Settings
from astra.db import SCHEMA_VERSION, initialize_database, probe_database, read_snapshot
from astra.importer import install_history
from astra.reads import ApiError, replay_state
from astra.routes import router

logger = logging.getLogger("astra")


class Health(BaseModel):
    status: Literal["ok", "unavailable"]
    database_ready: bool
    dataset_ready: bool


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.schema_ready = False
        app.state.source_status = "UNAVAILABLE"
        try:
            initialize_database(settings.database_path)
            app.state.schema_ready = True
        except (OSError, sqlite3.Error):
            logger.exception("Could not initialize SQLite")
        if app.state.schema_ready:
            try:
                result = install_history(settings.database_path, settings.dataset_dir)
                app.state.source_status = "VERIFIED"
                logger.info("Historical mission dataset: %s", result)
            except OSError:
                logger.warning("Source bundle unavailable. Set ASTRA_DATASET_DIR to the extracted dataset directory.")
            except (ValueError, csv.Error, sqlite3.Error) as exc:
                app.state.source_status = "INVALID"
                logger.error("Historical dataset was not installed: %s", exc)
        yield

    app = FastAPI(title="ASTRA 2.0", version="1.0", lifespan=lifespan,
                  openapi_url="/api/openapi.json", docs_url=None, redoc_url=None)
    app.state.database_path = settings.database_path
    if settings.environment == "development":
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET"], allow_headers=["Accept"])

    @app.middleware("http")
    async def no_cache(request: Request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ApiError)
    async def domain_error(_request: Request, exc: ApiError) -> JSONResponse:
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(sqlite3.Error)
    async def unavailable_database(_request: Request, exc: sqlite3.Error) -> JSONResponse:
        logger.warning("Mission SQLite read failed: %s", exc.__class__.__name__)
        return error(503, "database_unavailable", "Mission storage is unavailable.")

    @app.exception_handler(HTTPException)
    async def http_error(_request: Request, exc: HTTPException) -> JSONResponse:
        code, message = {
            404: ("not_found", "Endpoint not found."),
            405: ("method_not_allowed", "Method not allowed."),
        }.get(exc.status_code, ("request_failed", "The request could not be completed."))
        return error(exc.status_code, code, message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request: Request, _exception: RequestValidationError) -> JSONResponse:
        return error(422, "invalid_request", "The request did not match the API contract.")

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exception: Exception) -> JSONResponse:
        logger.error("Unhandled %s request", request.method, exc_info=exception)
        return error(500, "internal_error", "ASTRA could not complete the request.")

    @app.get("/api/health", responses={503: {"model": Health}})
    def health(response: Response) -> Health:
        try:
            with read_snapshot(settings.database_path) as connection:
                if not app.state.schema_ready or probe_database(connection) != SCHEMA_VERSION:
                    raise sqlite3.DatabaseError("Unexpected database schema")
                try:
                    replay_state(connection)
                    ready = True
                except ApiError:
                    ready = False
        except (OSError, sqlite3.Error) as exc:
            logger.warning("SQLite readiness probe failed: %s", exc.__class__.__name__)
            response.status_code = 503
            return Health(status="unavailable", database_ready=False, dataset_ready=False)
        return Health(status="ok", database_ready=True, dataset_ready=ready)

    app.include_router(router)
    return app
