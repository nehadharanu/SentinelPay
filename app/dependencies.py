import uuid
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import Forbidden, InvalidToken
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.ai_scorer import AIScorer
from app.services.behavioral_profiler import BehavioralProfiler
from app.services.fraud_engine import FraudEngine
from app.services.rule_engine import RuleEngine

_bearer = HTTPBearer()

_redis_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    """Return the shared async Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    return _redis_client


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Decode the Bearer JWT and return the authenticated User.

    Raises InvalidToken if the token is missing or malformed.
    """
    from sqlalchemy import select

    user_id_str = decode_access_token(credentials.credentials)
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise InvalidToken()

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise InvalidToken()
    return user


async def require_admin(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """Require the authenticated user to have the admin role."""
    if current_user.role != "admin":
        raise Forbidden()
    return current_user


def get_fraud_engine(
    db: Annotated[AsyncSession, Depends(get_db)],
    redis_client: Annotated[aioredis.Redis, Depends(get_redis)],
) -> FraudEngine:
    """Construct and return a FraudEngine with all three layer services injected."""
    from app.db.session import AsyncSessionLocal

    rule_engine = RuleEngine(redis_client=redis_client, db_session_factory=AsyncSessionLocal)
    behavioral_profiler = BehavioralProfiler(redis_client=redis_client)
    ai_scorer = AIScorer()
    return FraudEngine(
        rule_engine=rule_engine,
        behavioral_profiler=behavioral_profiler,
        ai_scorer=ai_scorer,
    )
