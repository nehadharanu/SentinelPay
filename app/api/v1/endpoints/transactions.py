import math
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import Forbidden
from app.db.session import get_db
from app.dependencies import get_current_user, get_fraud_engine
from app.models.user import User
from app.schemas.fraud import (
    AIScorerLayer,
    BehavioralProfilerLayer,
    FraudDecisionDetailResponse,
    FraudDecisionResponse,
    LayersResponse,
    RuleEngineLayer,
)
from app.schemas.transaction import TransactionCreate, TransactionResponse
from app.services.fraud_engine import FraudEngine
from app.services.transaction_service import TransactionService

router = APIRouter()


def _build_layers(rule_result, behavioral_result, ai_result) -> LayersResponse:
    """Construct a LayersResponse from the three individual layer results."""
    skipped = ai_result.skipped if ai_result else True
    return LayersResponse(
        rule_engine=RuleEngineLayer(
            result=rule_result.result,
            reasons=rule_result.reasons,
        ),
        behavioral_profiler=BehavioralProfilerLayer(
            behavioral_score=round(behavioral_result.behavioral_score, 3),
            anomalies=behavioral_result.anomalies,
        ),
        ai_scorer=AIScorerLayer(
            risk_score=None if skipped else ai_result.risk_score,
            risk_level=None if skipped else ai_result.risk_level,
            explanation=None if skipped else ai_result.explanation,
            skipped=skipped,
        ),
    )


@router.post("/analyze", response_model=FraudDecisionResponse)
async def analyze_transaction(
    body: TransactionCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    fraud_engine: Annotated[FraudEngine, Depends(get_fraud_engine)],
) -> FraudDecisionResponse:
    """Submit a transaction for fraud analysis and return a complete fraud decision."""
    svc = TransactionService(db)
    tx = await svc.create(body, current_user.merchant_id)
    result = await fraud_engine.analyze(body)
    decision = await svc.save_decision(tx, result)

    return FraudDecisionResponse(
        transaction_id=tx.id,
        external_transaction_id=tx.external_transaction_id,
        final_decision=result.final_decision,
        recommended_action=result.recommended_action,
        processing_ms=result.processing_ms,
        layers=_build_layers(result.rule_result, result.behavioral_result, result.ai_result),
        created_at=decision.created_at,
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TransactionResponse:
    """Retrieve a single transaction by UUID; merchants may only access their own."""
    svc = TransactionService(db)
    tx = await svc.get_by_id(transaction_id)
    if current_user.role != "admin" and tx.merchant_id != current_user.merchant_id:
        raise Forbidden()
    return tx


@router.get("/", response_model=dict)
async def list_transactions(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    final_decision: str | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    merchant_id: str | None = Query(None),
) -> dict:
    """List transactions with pagination; merchants see only their own records."""
    effective_merchant_id = (
        merchant_id if current_user.role == "admin" else current_user.merchant_id
    )
    svc = TransactionService(db)
    items, total = await svc.list_transactions(
        merchant_id=effective_merchant_id,
        final_decision=final_decision,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [TransactionResponse.model_validate(t) for t in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(total / page_size) if total else 1,
    }


@router.get("/{transaction_id}/decision", response_model=FraudDecisionDetailResponse)
async def get_decision(
    transaction_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FraudDecisionDetailResponse:
    """Return the fraud decision record for a given transaction UUID."""
    svc = TransactionService(db)
    tx = await svc.get_by_id(transaction_id)
    if current_user.role != "admin" and tx.merchant_id != current_user.merchant_id:
        raise Forbidden()
    decision = await svc.get_decision_by_transaction_id(transaction_id)

    layers = LayersResponse(
        rule_engine=RuleEngineLayer(
            result=decision.layer1_result,
            reasons=decision.layer1_reasons or [],
        ),
        behavioral_profiler=BehavioralProfilerLayer(
            behavioral_score=float(decision.layer2_behavioral_score),
            anomalies=decision.layer2_anomalies or [],
        ),
        ai_scorer=AIScorerLayer(
            risk_score=decision.layer3_risk_score,
            risk_level=decision.layer3_risk_level,
            explanation=decision.layer3_explanation,
            skipped=decision.layer3_risk_score is None,
        ),
    )
    return FraudDecisionDetailResponse(
        id=decision.id,
        transaction_id=decision.transaction_id,
        final_decision=decision.final_decision,
        recommended_action=decision.recommended_action,
        processing_ms=decision.processing_ms,
        layers=layers,
        created_at=decision.created_at,
    )
