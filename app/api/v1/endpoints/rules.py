import math
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RuleNameAlreadyExists, RuleNotFound
from app.db.session import get_db
from app.dependencies import require_admin
from app.models.rule import Rule
from app.models.user import User
from app.schemas.rule import PaginatedRules, RuleCreate, RuleResponse, RuleToggle, RuleUpdate

router = APIRouter()


@router.get("/", response_model=PaginatedRules)
async def list_rules(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    rule_type: str | None = Query(None),
    is_active: bool | None = Query(None),
) -> PaginatedRules:
    """List all fraud detection rules with optional filtering."""
    query = select(Rule)
    if rule_type:
        query = query.where(Rule.rule_type == rule_type)
    if is_active is not None:
        query = query.where(Rule.is_active == is_active)

    from sqlalchemy import func
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = await db.execute(query.offset(offset).limit(page_size))
    items = rows.scalars().all()

    return PaginatedRules(
        items=[RuleResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 1,
    )


@router.post("/", response_model=RuleResponse, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Rule:
    """Create a new fraud detection rule."""
    existing = await db.execute(select(Rule).where(Rule.name == body.name))
    if existing.scalar_one_or_none():
        raise RuleNameAlreadyExists()

    rule = Rule(
        id=uuid.uuid4(),
        name=body.name,
        rule_type=body.rule_type,
        condition=body.condition,
        action=body.action,
        is_active=body.is_active,
        created_by=admin.id,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.put("/{rule_id}", response_model=RuleResponse)
async def update_rule(
    rule_id: uuid.UUID,
    body: RuleUpdate,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Rule:
    """Update an existing rule; only provided fields are changed."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise RuleNotFound()

    for field_name, value in body.model_dump(exclude_none=True).items():
        setattr(rule, field_name, value)

    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(
    rule_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Permanently delete a fraud detection rule."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise RuleNotFound()

    await db.delete(rule)
    await db.commit()


@router.put("/{rule_id}/toggle", response_model=RuleResponse)
async def toggle_rule(
    rule_id: uuid.UUID,
    body: RuleToggle,
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Rule:
    """Enable or disable a rule without deleting it."""
    result = await db.execute(select(Rule).where(Rule.id == rule_id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise RuleNotFound()

    rule.is_active = body.is_active
    await db.commit()
    await db.refresh(rule)
    return rule
