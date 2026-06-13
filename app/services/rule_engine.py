import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

import redis.asyncio as aioredis

from app.config import settings
from app.schemas.transaction import TransactionCreate

logger = logging.getLogger(__name__)


@dataclass
class RuleResult:
    """Output of Layer 1 rule evaluation."""

    result: Literal["PASS", "FLAG", "BLOCK"]
    reasons: list[str] = field(default_factory=list)


class RuleEngine:
    """Layer 1: deterministic rule evaluation engine.

    Evaluates blacklist, amount, velocity, and geo rules in order.
    Rules from the database are cached in memory and refreshed every
    RULES_CACHE_TTL_SECONDS seconds.
    """

    def __init__(self, redis_client: aioredis.Redis, db_session_factory):
        """Initialise with a Redis client and an async DB session factory."""
        self._redis = redis_client
        self._db_factory = db_session_factory
        self._rules_cache: list[dict] = []
        self._cache_loaded_at: float = 0.0

    async def _load_rules(self) -> None:
        """Reload active rules from the database into the in-memory cache."""
        from app.models.rule import Rule
        from sqlalchemy import select

        async with self._db_factory() as session:
            result = await session.execute(select(Rule).where(Rule.is_active == True))
            rows = result.scalars().all()
            self._rules_cache = [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "rule_type": r.rule_type,
                    "condition": r.condition,
                    "action": r.action,
                }
                for r in rows
            ]
        self._cache_loaded_at = asyncio.get_event_loop().time()

    async def _get_rules(self) -> list[dict]:
        """Return cached rules, refreshing if the TTL has elapsed."""
        now = asyncio.get_event_loop().time()
        if now - self._cache_loaded_at > settings.RULES_CACHE_TTL_SECONDS:
            await self._load_rules()
        return self._rules_cache

    async def evaluate(self, tx: TransactionCreate) -> RuleResult:
        """Evaluate all active rules against the transaction and return a RuleResult.

        Evaluation order: blacklists → amount → velocity → geo.
        Returns BLOCK immediately if any BLOCK trigger fires.
        """
        reasons: list[str] = []
        has_block = False
        has_flag = False

        block_reasons = await self._check_blacklists(tx)
        if block_reasons:
            return RuleResult(result="BLOCK", reasons=block_reasons)

        rules = await self._get_rules()

        for rule in rules:
            rtype = rule["rule_type"]
            action = rule["action"]
            cond = rule["condition"]

            triggered = False
            reason_code = ""

            if rtype == "amount":
                triggered, reason_code = self._check_amount(tx, cond)
            elif rtype == "velocity":
                triggered, reason_code = await self._check_velocity(tx, cond)
            elif rtype == "geo":
                triggered, reason_code = await self._check_geo(tx, cond)

            if triggered and reason_code:
                reasons.append(reason_code)
                if action == "BLOCK":
                    has_block = True
                else:
                    has_flag = True

        # Fallback: if no amount rules were loaded from the DB, enforce the
        # hard-coded limits from settings so a fresh/empty rules table still
        # provides basic amount protection.
        if not any(r["rule_type"] == "amount" for r in rules):
            amount_f = float(tx.amount)
            if amount_f > settings.AMOUNT_HARD_LIMIT:
                reasons.append("AMOUNT_EXCEEDS_HARD_LIMIT")
                has_block = True
            elif amount_f > settings.AMOUNT_SOFT_LIMIT:
                reasons.append("AMOUNT_EXCEEDS_SOFT_LIMIT")
                has_flag = True

        if not reasons:
            return RuleResult(result="PASS", reasons=[])
        if has_block:
            return RuleResult(result="BLOCK", reasons=reasons)
        return RuleResult(result="FLAG", reasons=reasons)

    async def _check_blacklists(self, tx: TransactionCreate) -> list[str]:
        """Check Redis blacklists for card, IP, and device. Return reason codes for any hits."""
        reasons = []
        if await self._redis.sismember("sentinelpay:blacklist:cards", tx.card_last4):
            reasons.append("BLACKLISTED_CARD")
        if await self._redis.sismember("sentinelpay:blacklist:ips", tx.ip_address):
            reasons.append("BLACKLISTED_IP")
        if await self._redis.sismember("sentinelpay:blacklist:devices", tx.device_fingerprint):
            reasons.append("BLACKLISTED_DEVICE")
        return reasons

    def _check_amount(self, tx: TransactionCreate, cond: dict) -> tuple[bool, str]:
        """Check if the transaction amount exceeds the rule threshold."""
        threshold = float(cond.get("threshold", 0))
        if float(tx.amount) > threshold:
            code = (
                "AMOUNT_EXCEEDS_HARD_LIMIT"
                if threshold >= settings.AMOUNT_HARD_LIMIT
                else "AMOUNT_EXCEEDS_SOFT_LIMIT"
            )
            return True, code
        return False, ""

    async def _check_velocity(self, tx: TransactionCreate, cond: dict) -> tuple[bool, str]:
        """Check transaction velocity for the card within the rule's time window."""
        window_seconds = int(cond.get("window_seconds", 3600))
        threshold = int(cond.get("threshold", 5))
        window_label = "1h" if window_seconds <= 3600 else "24h"
        key = f"sentinelpay:velocity:{tx.card_last4}:{window_label}"
        count_raw = await self._redis.get(key)
        count = int(count_raw) if count_raw else 0
        if count >= threshold:
            code = "VELOCITY_1H_EXCEEDED" if window_label == "1h" else "VELOCITY_24H_EXCEEDED"
            return True, code
        return False, ""

    async def _check_geo(self, tx: TransactionCreate, cond: dict) -> tuple[bool, str]:
        """Check for impossible travel by comparing with the last known location."""
        from app.utils.geo import is_impossible_travel

        if tx.latitude is None or tx.longitude is None:
            return False, ""

        profile_key = f"sentinelpay:profile:{tx.card_last4}"
        last_country = await self._redis.hget(profile_key, "last_tx_country")
        last_lat_raw = await self._redis.hget(profile_key, "last_tx_lat")
        last_lon_raw = await self._redis.hget(profile_key, "last_tx_lon")
        last_ts_raw = await self._redis.hget(profile_key, "last_tx_timestamp")

        if not all([last_country, last_lat_raw, last_lon_raw, last_ts_raw]):
            return False, ""

        last_country_str = last_country.decode() if isinstance(last_country, bytes) else last_country
        if last_country_str == tx.country_code:
            return False, ""

        try:
            last_lat = float(last_lat_raw)
            last_lon = float(last_lon_raw)
            last_ts_str = last_ts_raw.decode() if isinstance(last_ts_raw, bytes) else last_ts_raw
            last_ts = datetime.fromisoformat(last_ts_str)
        except (ValueError, TypeError):
            return False, ""

        now = datetime.now(timezone.utc)
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        hours_elapsed = (now - last_ts).total_seconds() / 3600

        max_distance_km = float(cond.get("max_distance_km", settings.IMPOSSIBLE_TRAVEL_KM))
        min_hours = float(cond.get("min_hours", settings.IMPOSSIBLE_TRAVEL_HOURS))

        if is_impossible_travel(
            last_lat, last_lon, tx.latitude, tx.longitude, hours_elapsed, max_distance_km, min_hours
        ):
            return True, "IMPOSSIBLE_TRAVEL"
        return False, ""

    # ── Blacklist management methods ──────────────────────────────────────────

    async def add_card_to_blacklist(self, card_last4: str) -> None:
        """Add a card's last 4 digits to the Redis blacklist."""
        await self._redis.sadd("sentinelpay:blacklist:cards", card_last4)

    async def remove_card_from_blacklist(self, card_last4: str) -> None:
        """Remove a card's last 4 digits from the Redis blacklist."""
        await self._redis.srem("sentinelpay:blacklist:cards", card_last4)

    async def add_ip_to_blacklist(self, ip: str) -> None:
        """Add an IP address to the Redis blacklist."""
        await self._redis.sadd("sentinelpay:blacklist:ips", ip)

    async def remove_ip_from_blacklist(self, ip: str) -> None:
        """Remove an IP address from the Redis blacklist."""
        await self._redis.srem("sentinelpay:blacklist:ips", ip)

    async def add_device_to_blacklist(self, fingerprint: str) -> None:
        """Add a device fingerprint to the Redis blacklist."""
        await self._redis.sadd("sentinelpay:blacklist:devices", fingerprint)

    async def remove_device_from_blacklist(self, fingerprint: str) -> None:
        """Remove a device fingerprint from the Redis blacklist."""
        await self._redis.srem("sentinelpay:blacklist:devices", fingerprint)
