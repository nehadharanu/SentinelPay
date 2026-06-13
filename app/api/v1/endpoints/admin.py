import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CannotDemoteSelf, UserNotFound
from app.db.session import get_db
from app.dependencies import require_admin
from app.models.fraud_decision import FraudDecision
from app.models.user import User
from app.schemas.auth import UserResponse

router = APIRouter()


class UserRoleUpdate(BaseModel):
    """Request body for PUT /admin/users/{user_id}/role."""

    role: str | None = None
    is_active: bool | None = None


@router.get("/metrics")
async def get_metrics(
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
) -> dict:
    """Return system-wide fraud detection metrics for the specified time window."""
    if not from_date:
        from_date = datetime.now(timezone.utc) - timedelta(hours=24)
    if not to_date:
        to_date = datetime.now(timezone.utc)

    base_q = select(FraudDecision).where(
        FraudDecision.created_at >= from_date,
        FraudDecision.created_at <= to_date,
    )
    rows = (await db.execute(base_q)).scalars().all()
    total = len(rows)

    approved = sum(1 for r in rows if r.final_decision == "APPROVE")
    flagged = sum(1 for r in rows if r.final_decision == "FLAG")
    reviewed = sum(1 for r in rows if r.final_decision == "REVIEW")
    blocked = sum(1 for r in rows if r.final_decision == "BLOCK")

    layer1_flags = sum(1 for r in rows if r.layer1_result == "FLAG")
    layer1_blocks = sum(1 for r in rows if r.layer1_result == "BLOCK")
    layer3_skipped = sum(1 for r in rows if r.layer3_risk_score is None)

    avg_beh = (
        sum(float(r.layer2_behavioral_score) for r in rows) / total if total else 0.0
    )
    scored_rows = [r for r in rows if r.layer3_risk_score is not None]
    avg_risk = (
        sum(r.layer3_risk_score for r in scored_rows) / len(scored_rows)
        if scored_rows
        else 0
    )

    latencies = sorted(r.processing_ms for r in rows)
    avg_ms = sum(latencies) / total if total else 0
    p95_ms = latencies[int(0.95 * len(latencies))] if latencies else 0
    p99_ms = latencies[int(0.99 * len(latencies))] if latencies else 0

    def rate(n: int) -> float:
        """Calculate percentage rate rounded to 2 decimal places."""
        return round(n / total * 100, 2) if total else 0.0

    return {
        "period": {"from": from_date.isoformat(), "to": to_date.isoformat()},
        "totals": {
            "transactions_analyzed": total,
            "approved": approved,
            "flagged": flagged,
            "reviewed": reviewed,
            "blocked": blocked,
        },
        "rates": {
            "approval_rate": rate(approved),
            "flag_rate": rate(flagged),
            "review_rate": rate(reviewed),
            "block_rate": rate(blocked),
        },
        "layer_triggers": {
            "layer1_flags": layer1_flags,
            "layer1_blocks": layer1_blocks,
            "layer2_avg_score": round(avg_beh, 3),
            "layer3_avg_risk_score": round(avg_risk, 1),
            "layer3_skipped": layer3_skipped,
        },
        "performance": {
            "avg_processing_ms": round(avg_ms),
            "p95_processing_ms": p95_ms,
            "p99_processing_ms": p99_ms,
        },
    }


@router.get("/users")
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    role: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> dict:
    """List all registered users with optional role and active-status filters."""
    query = select(User)
    if role:
        query = query.where(User.role == role)
    if is_active is not None:
        query = query.where(User.is_active == is_active)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return {
        "items": [UserResponse.model_validate(u) for u in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
    }


@router.put("/users/{user_id}/role", response_model=UserResponse)
async def update_user_role(
    user_id: uuid.UUID,
    body: UserRoleUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Update a user's role or active status; admins cannot remove their own admin role."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise UserNotFound()

    if body.role and body.role != "admin" and str(user.id) == str(admin.id):
        raise CannotDemoteSelf()

    if body.role:
        user.role = body.role
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.commit()
    await db.refresh(user)
    return user
