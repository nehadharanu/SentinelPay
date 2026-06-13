import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FraudDecision(Base):
    """ORM model for the fraud_decisions table."""

    __tablename__ = "fraud_decisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("transactions.id"), unique=True, nullable=False
    )
    layer1_result: Mapped[str] = mapped_column(
        Enum("PASS", "FLAG", "BLOCK", name="layer1_result_enum"), nullable=False
    )
    layer1_reasons: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    layer2_behavioral_score: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    layer2_anomalies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    layer3_risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    layer3_risk_level: Mapped[str | None] = mapped_column(
        Enum("LOW", "MEDIUM", "HIGH", "CRITICAL", name="risk_level_enum"), nullable=True
    )
    layer3_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_decision: Mapped[str] = mapped_column(
        Enum("APPROVE", "FLAG", "REVIEW", "BLOCK", name="final_decision_enum"), nullable=False
    )
    recommended_action: Mapped[str] = mapped_column(String(255), nullable=False)
    processing_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
