from fastapi import APIRouter

from app.api.v1.routes import health, jobs

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(jobs.router, tags=["jobs"])
