import uuid
from datetime import datetime

from pydantic import BaseModel


class RuleCreate(BaseModel):
    """Request body for POST /rules/."""

    name: str
    rule_type: str
    condition: dict
    action: str
    is_active: bool = True


class RuleUpdate(BaseModel):
    """Request body for PUT /rules/{rule_id}. All fields optional."""

    name: str | None = None
    rule_type: str | None = None
    condition: dict | None = None
    action: str | None = None
    is_active: bool | None = None


class RuleToggle(BaseModel):
    """Request body for PUT /rules/{rule_id}/toggle."""

    is_active: bool


class RuleResponse(BaseModel):
    """Response schema for a rule record."""

    id: uuid.UUID
    name: str
    rule_type: str
    condition: dict
    action: str
    is_active: bool
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedRules(BaseModel):
    """Paginated list of rules."""

    items: list[RuleResponse]
    total: int
    page: int
    page_size: int
    pages: int
