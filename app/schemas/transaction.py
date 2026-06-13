import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator


class TransactionCreate(BaseModel):
    """Request body for POST /transactions/analyze."""

    external_transaction_id: str
    amount: Decimal
    currency: str
    card_last4: str
    card_bin: str
    cardholder_name: str
    merchant_category_code: str
    merchant_name: str
    ip_address: str
    device_fingerprint: str
    country_code: str
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @field_validator("amount")
    @classmethod
    def amount_positive(cls, v: Decimal) -> Decimal:
        """Ensure amount is positive."""
        if v <= 0:
            raise ValueError("amount must be positive.")
        return v

    @field_validator("currency")
    @classmethod
    def currency_format(cls, v: str) -> str:
        """Ensure currency is a 3-letter uppercase code."""
        if len(v) != 3 or not v.isalpha():
            raise ValueError("currency must be a 3-letter ISO-4217 code.")
        return v.upper()

    @field_validator("card_last4")
    @classmethod
    def card_last4_format(cls, v: str) -> str:
        """Ensure card_last4 is exactly 4 digits."""
        import re
        if not re.match(r"^\d{4}$", v):
            raise ValueError("card_last4 must be exactly 4 digits.")
        return v

    @field_validator("card_bin")
    @classmethod
    def card_bin_format(cls, v: str) -> str:
        """Ensure card_bin is 6–8 digits."""
        import re
        if not re.match(r"^\d{6,8}$", v):
            raise ValueError("card_bin must be 6–8 digits.")
        return v

    @field_validator("merchant_category_code")
    @classmethod
    def mcc_format(cls, v: str) -> str:
        """Ensure MCC is exactly 4 digits."""
        import re
        if not re.match(r"^\d{4}$", v):
            raise ValueError("merchant_category_code must be exactly 4 digits.")
        return v

    @field_validator("country_code")
    @classmethod
    def country_code_format(cls, v: str) -> str:
        """Ensure country_code is 2 uppercase letters."""
        if len(v) != 2 or not v.isalpha():
            raise ValueError("country_code must be a 2-letter ISO-3166-1 alpha-2 code.")
        return v.upper()

    @field_validator("ip_address")
    @classmethod
    def ip_address_valid(cls, v: str) -> str:
        """Ensure ip_address is a valid IPv4 or IPv6 address."""
        import ipaddress
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError("ip_address must be a valid IPv4 or IPv6 address.")
        return v

    @field_validator("latitude")
    @classmethod
    def latitude_range(cls, v: float | None) -> float | None:
        """Ensure latitude is between -90 and 90."""
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("latitude must be between -90 and 90.")
        return v

    @field_validator("longitude")
    @classmethod
    def longitude_range(cls, v: float | None) -> float | None:
        """Ensure longitude is between -180 and 180."""
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("longitude must be between -180 and 180.")
        return v


class TransactionResponse(BaseModel):
    """Response schema for a persisted transaction record."""

    id: uuid.UUID
    external_transaction_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    card_last4: str
    card_bin: str
    cardholder_name: str
    merchant_category_code: str
    merchant_name: str
    ip_address: str
    device_fingerprint: str
    country_code: str
    city: str | None
    latitude: float | None
    longitude: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
