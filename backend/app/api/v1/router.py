from fastapi import APIRouter

from app.api.v1.routes import health, jobs, events

api_v1_router = APIRouter(prefix="/api")

api_v1_router.include_router(health.router, tags=["health"])
api_v1_router.include_router(jobs.router, tags=["jobs"])
api_v1_router.include_router(events.router, tags=["events"])
