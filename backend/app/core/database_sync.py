from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Convert async URL to sync for Celery workers
_sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")

sync_engine = create_engine(
    _sync_url,
    echo=settings.DATABASE_ECHO,
    pool_pre_ping=True,
    pool_size=3,
    max_overflow=5,
)

SyncSessionFactory = sessionmaker(bind=sync_engine, class_=Session)


def get_sync_db() -> Session:
    """Get a synchronous database session for use in Celery workers."""
    return SyncSessionFactory()
