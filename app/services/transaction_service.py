import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DecisionNotFound, DuplicateTransaction, TransactionNotFound
from app.models.fraud_decision import FraudDecision
from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.fraud_engine import FraudDecisionResult


class TransactionService:
    """CRUD and persistence layer for transactions and fraud decisions."""

    def __init__(self, db: AsyncSession):
        """Initialise with an async database session."""
        self._db = db

    async def create(self, tx_data: TransactionCreate, merchant_id: str) -> Transaction:
        """Persist a new transaction record; raise DuplicateTransaction on idempotency conflict."""
        existing = await self._db.execute(
            select(Transaction).where(
                Transaction.external_transaction_id == tx_data.external_transaction_id
            )
        )
        if existing.scalar_one_or_none():
            raise DuplicateTransaction()

        tx = Transaction(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            external_transaction_id=tx_data.external_transaction_id,
            amount=tx_data.amount,
            currency=tx_data.currency,
            card_last4=tx_data.card_last4,
            card_bin=tx_data.card_bin,
            cardholder_name=tx_data.cardholder_name,
            merchant_category_code=tx_data.merchant_category_code,
            merchant_name=tx_data.merchant_name,
            ip_address=tx_data.ip_address,
            device_fingerprint=tx_data.device_fingerprint,
            country_code=tx_data.country_code,
            city=tx_data.city,
            latitude=tx_data.latitude,
            longitude=tx_data.longitude,
        )
        self._db.add(tx)
        await self._db.flush()
        return tx

    async def save_decision(
        self, transaction: Transaction, result: FraudDecisionResult
    ) -> FraudDecision:
        """Persist a FraudDecision record linked to the given transaction."""
        ai = result.ai_result
        decision = FraudDecision(
            id=uuid.uuid4(),
            transaction_id=transaction.id,
            layer1_result=result.rule_result.result,
            layer1_reasons=result.rule_result.reasons,
            layer2_behavioral_score=result.behavioral_result.behavioral_score,
            layer2_anomalies=result.behavioral_result.anomalies,
            layer3_risk_score=ai.risk_score if ai and not ai.skipped else None,
            layer3_risk_level=ai.risk_level if ai and not ai.skipped else None,
            layer3_explanation=ai.explanation if ai and not ai.skipped else None,
            final_decision=result.final_decision,
            recommended_action=result.recommended_action,
            processing_ms=result.processing_ms,
        )
        self._db.add(decision)
        await self._db.commit()
        await self._db.refresh(transaction)
        await self._db.refresh(decision)
        return decision

    async def get_by_id(self, transaction_id: uuid.UUID) -> Transaction:
        """Return a transaction by UUID; raise TransactionNotFound if absent."""
        result = await self._db.execute(
            select(Transaction).where(Transaction.id == transaction_id)
        )
        tx = result.scalar_one_or_none()
        if not tx:
            raise TransactionNotFound()
        return tx

    async def get_decision_by_transaction_id(
        self, transaction_id: uuid.UUID
    ) -> FraudDecision:
        """Return the fraud decision for a transaction; raise DecisionNotFound if absent."""
        result = await self._db.execute(
            select(FraudDecision).where(FraudDecision.transaction_id == transaction_id)
        )
        decision = result.scalar_one_or_none()
        if not decision:
            raise DecisionNotFound()
        return decision

    async def list_transactions(
        self,
        merchant_id: str | None,
        final_decision: str | None,
        from_date: datetime | None,
        to_date: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Transaction], int]:
        """Return a paginated list of transactions filtered by the given criteria."""
        query = select(Transaction)
        if merchant_id:
            query = query.where(Transaction.merchant_id == merchant_id)
        if final_decision:
            query = query.join(FraudDecision, FraudDecision.transaction_id == Transaction.id).where(
                FraudDecision.final_decision == final_decision
            )
        if from_date:
            query = query.where(Transaction.created_at >= from_date)
        if to_date:
            query = query.where(Transaction.created_at <= to_date)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self._db.execute(count_query)
        total = total_result.scalar_one()

        offset = (page - 1) * page_size
        query = query.order_by(Transaction.created_at.desc()).offset(offset).limit(page_size)
        rows = await self._db.execute(query)
        return rows.scalars().all(), total
