import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.v1.router import router as v1_router
from app.config import settings
from app.core.exceptions import SentinelPayException
from app.db.init_db import init_db
from app.dependencies import get_redis

logging.basicConfig(level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks (DB init, Redis ping) and teardown on shutdown."""
    await init_db()
    redis = get_redis()
    await redis.ping()
    logger.info("SentinelPay started. Environment: %s", settings.ENVIRONMENT)
    yield
    await redis.aclose()
    logger.info("SentinelPay shutdown complete.")


app = FastAPI(
    title="SentinelPay",
    description="AI-powered payment fraud detection engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(v1_router, prefix="/api/v1")


@app.exception_handler(SentinelPayException)
async def sentinelpay_exception_handler(request: Request, exc: SentinelPayException):
    """Return structured error envelopes for all SentinelPay domain exceptions."""
    return JSONResponse(status_code=exc.status_code, content=exc.detail)


@app.get("/health", tags=["health"])
async def health_check() -> dict:
    """Return service health including database and Redis connectivity status."""
    from app.db.session import engine

    db_status = "ok"
    redis_status = "ok"

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    except Exception:
        db_status = "error"

    try:
        redis = get_redis()
        await redis.ping()
    except Exception:
        redis_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    status_code = 200 if overall == "ok" else 503

    from fastapi.responses import JSONResponse as JR
    return JR(
        content={"status": overall, "version": "1.0.0", "database": db_status, "redis": redis_status},
        status_code=status_code,
    )
