from fastapi import APIRouter

from app.api.v1 import admin, artifacts, categories, discovery, me, sources, system, topics, volunteering

api_router = APIRouter(prefix="/api/v1")
for module in (system, categories, sources, topics, discovery, volunteering, artifacts, me, admin):
    api_router.include_router(module.router)
