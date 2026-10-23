"""Domain errors and the single JSON error format used by every endpoint.

    {"error": {"code": "not_found", "message": "...", "details": ..., "request_id": "..."}}
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import request_id_var

log = logging.getLogger("techradar.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: Any = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class InvalidState(AppError):
    status_code, code = 409, "invalid_state"


class Gone(AppError):
    status_code, code = 410, "gone"


class PayloadTooLarge(AppError):
    status_code, code = 413, "payload_too_large"


class Unprocessable(AppError):
    status_code, code = 422, "unprocessable"


class ServiceUnavailable(AppError):
    status_code, code = 503, "service_unavailable"


_HTTP_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
               409: "conflict", 413: "payload_too_large", 422: "validation_error", 429: "rate_limited"}


def _body(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details, "request_id": request_id_var.get()}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code, headers=headers)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body(_HTTP_CODES.get(exc.status_code, "http_error"), str(exc.detail)),
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        # only location/message/type: never echo submitted values back (they may contain secrets)
        details = [{"loc": [str(p) for p in e.get("loc", [])], "message": e.get("msg", ""), "type": e.get("type", "")}
                   for e in exc.errors()]
        return JSONResponse(_body("validation_error", "The request is not valid", details), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("Unhandled error", extra={"request_id": request_id_var.get()})
        return JSONResponse(_body("internal_error", "Something went wrong on our side"), status_code=500)
