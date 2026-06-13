import uuid
from datetime import datetime

from pydantic import BaseModel


class RuleEngineLayer(BaseModel):
    """Layer 1 rule engine summary within a fraud decision response."""

    result: str
    reasons: list[str]


class BehavioralProfilerLayer(BaseModel):
    """Layer 2 behavioral profiler summary within a fraud decision response."""

    behavioral_score: float
    anomalies: list[str]


class AIScorerLayer(BaseModel):
    """Layer 3 AI scorer summary within a fraud decision response."""

    risk_score: int | None
    risk_level: str | None
    explanation: str | None
    skipped: bool


class LayersResponse(BaseModel):
    """Container for all three layer results in a fraud decision response."""

    rule_engine: RuleEngineLayer
    behavioral_profiler: BehavioralProfilerLayer
    ai_scorer: AIScorerLayer


class FraudDecisionResponse(BaseModel):
    """Full fraud decision response returned from POST /transactions/analyze."""

    transaction_id: uuid.UUID
    external_transaction_id: str
    final_decision: str
    recommended_action: str
    processing_ms: int
    layers: LayersResponse
    created_at: datetime


class FraudDecisionDetailResponse(BaseModel):
    """Fraud decision returned from GET /transactions/{id}/decision."""

    id: uuid.UUID
    transaction_id: uuid.UUID
    final_decision: str
    recommended_action: str
    processing_ms: int
    layers: LayersResponse
    created_at: datetime

    model_config = {"from_attributes": True}
