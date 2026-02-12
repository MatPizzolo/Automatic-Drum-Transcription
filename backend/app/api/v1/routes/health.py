from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.config import settings
from app.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint — verifies DB, Redis, and model availability."""
    health = {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "checks": {},
    }

    # Database check
    try:
        await db.execute(text("SELECT 1"))
        health["checks"]["database"] = {"status": "up"}
    except Exception as e:
        health["status"] = "degraded"
        health["checks"]["database"] = {"status": "down", "error": str(e)}
        logger.error("health_check_db_failed", error=str(e))

    # Redis check
    try:
        import redis.asyncio as aioredis

        r = aioredis.from_url(settings.REDIS_URL)
        await r.ping()
        await r.aclose()
        health["checks"]["redis"] = {"status": "up"}
    except Exception as e:
        health["status"] = "degraded"
        health["checks"]["redis"] = {"status": "down", "error": str(e)}
        logger.error("health_check_redis_failed", error=str(e))

    # Model availability check (just checks if path/URI is configured)
    health["checks"]["model"] = {
        "status": "configured",
        "version": settings.MODEL_VERSION,
        "uri": settings.MODEL_URI,
    }

    status_code = 200 if health["status"] == "healthy" else 503
    from fastapi.responses import JSONResponse

    return JSONResponse(content=health, status_code=status_code)
