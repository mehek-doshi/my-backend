"""FastAPI application factory."""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.context import client_ip_var, request_id_var
from app.core.errors import install_error_handlers


def create_app() -> FastAPI:
    settings = get_settings()  # raises on unsafe configuration (e.g. dev auth in production)
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = FastAPI(title=settings.app_name, version="1.0.0",
                  docs_url=None if settings.is_production else "/docs",
                  redoc_url=None, openapi_url=None if settings.is_production else "/openapi.json")
    if settings.cors_origin_list:
        app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list, allow_credentials=False,
                           allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type", "X-Request-ID"])

    max_body = settings.max_upload_bytes + 1024 * 1024  # file + multipart overhead

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        declared = request.headers.get("content-length", "")
        if declared.isdigit() and int(declared) > max_body:
            from fastapi.responses import JSONResponse
            return JSONResponse({"error": {"code": "payload_too_large", "message": "The request is too large", "details": None,
                                           "request_id": None}}, status_code=413)
        rid = request.headers.get("x-request-id", "")
        rid = rid if 8 <= len(rid) <= 64 and rid.replace("-", "").isalnum() else uuid.uuid4().hex
        t1, t2 = request_id_var.set(rid), client_ip_var.set(request.client.host if request.client else None)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(t1)
            client_ip_var.reset(t2)
        response.headers["X-Request-ID"] = rid
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    install_error_handlers(app)
    app.include_router(api_router)
    return app


app = create_app()
