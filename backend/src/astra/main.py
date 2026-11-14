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
from astra.db import probe_database

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
    async def lifespan(_app: FastAPI):
        try:
            probe_database(settings.database_path, initialize=True)
        except (OSError, sqlite3.Error):
            logger.exception("Could not initialize SQLite")
        yield

    app = FastAPI(title="ASTRA 2.0", version="1.0", lifespan=lifespan,
                  openapi_url="/api/openapi.json", docs_url=None, redoc_url=None)
    if settings.environment == "development":
        app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                           allow_methods=["GET"], allow_headers=["Accept"])

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
        response.headers["Cache-Control"] = "no-store"
        try:
            probe_database(settings.database_path)
        except (OSError, sqlite3.Error) as exc:
            logger.warning("SQLite readiness probe failed: %s", exc.__class__.__name__)
            response.status_code = 503
            return Health(status="unavailable", database_ready=False, dataset_ready=False)
        return Health(status="ok", database_ready=True, dataset_ready=False)

    return app
