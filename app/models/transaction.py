import uuid
from datetime import datetime

from sqlalchemy import DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Transaction(Base):
    """ORM model for the transactions table."""

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    external_transaction_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    card_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    card_bin: Mapped[str] = mapped_column(String(8), nullable=False)
    cardholder_name: Mapped[str] = mapped_column(String(255), nullable=False)
    merchant_category_code: Mapped[str] = mapped_column(String(4), nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str] = mapped_column(INET, nullable=False)
    device_fingerprint: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
