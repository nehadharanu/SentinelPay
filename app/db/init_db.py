from app.db.base import Base
from app.db.session import engine
import app.models  # noqa: F401 — registers all models with Base.metadata


async def init_db() -> None:
    """Create all database tables on application startup if they do not already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
