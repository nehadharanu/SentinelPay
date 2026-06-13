import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone

import redis.asyncio as aioredis

from app.schemas.transaction import TransactionCreate

logger = logging.getLogger(__name__)

PROFILE_TTL = 2592000  # 30 days


@dataclass
class BehavioralResult:
    """Output of Layer 2 behavioral profiling."""

    behavioral_score: float
    anomalies: list[str] = field(default_factory=list)


class BehavioralProfiler:
    """Layer 2: Redis-backed behavioral profiling and anomaly scoring.

    Reads the card's historical profile from Redis, scores anomalies,
    then updates the profile using Welford's online algorithm for
    rolling mean and standard deviation.
    """

    def __init__(self, redis_client: aioredis.Redis):
        """Initialise with an async Redis client."""
        self._redis = redis_client

    async def score(self, tx: TransactionCreate) -> BehavioralResult:
        """Score behavioral anomalies for the transaction and update the profile.

        Returns a BehavioralResult with a clamped 0.0–1.0 score and a list
        of anomaly codes that contributed to it.
        """
        key = f"sentinelpay:profile:{tx.card_last4}"
        profile = await self._load_profile(key)

        raw_score = 0.0
        anomalies: list[str] = []

        amount_f = float(tx.amount)
        avg_overall = float(profile.get("avg_amount_overall", 0) or 0)
        stddev = float(profile.get("stddev_amount", 0) or 0)
        tx_count_total = int(profile.get("tx_count_total", 0) or 0)

        if tx_count_total > 0:
            if avg_overall > 0 and amount_f > 3 * avg_overall:
                raw_score += 0.30
                anomalies.append("AMOUNT_SPIKE")
            elif stddev > 0 and amount_f > avg_overall + 2 * stddev:
                raw_score += 0.20
                anomalies.append("AMOUNT_DEVIATION")

        known_devices_raw = profile.get("known_devices", "[]")
        try:
            known_devices = json.loads(known_devices_raw) if known_devices_raw else []
        except (json.JSONDecodeError, TypeError):
            known_devices = []

        if tx_count_total > 0 and tx.device_fingerprint not in known_devices:
            raw_score += 0.20
            anomalies.append("NEW_DEVICE")

        known_countries_raw = profile.get("known_countries", "[]")
        try:
            known_countries = json.loads(known_countries_raw) if known_countries_raw else []
        except (json.JSONDecodeError, TypeError):
            known_countries = []

        if tx_count_total > 0 and tx.country_code not in known_countries:
            raw_score += 0.25
            anomalies.append("NEW_COUNTRY")

        tx_count_7d = int(profile.get("tx_count_7d", 0) or 0)
        if tx_count_total >= 14 and tx_count_7d > 2 * (tx_count_total / (tx_count_total / 7)):
            raw_score += 0.15
            anomalies.append("FREQUENCY_SPIKE")

        mcc_key = f"avg_amount_{tx.merchant_category_code}"
        if tx_count_total > 0 and not profile.get(mcc_key):
            raw_score += 0.10
            anomalies.append("NEW_MERCHANT_CATEGORY")

        behavioral_score = min(raw_score, 1.0)

        await self._update_profile(key, tx, profile, known_devices, known_countries)

        return BehavioralResult(behavioral_score=behavioral_score, anomalies=anomalies)

    async def _load_profile(self, key: str) -> dict:
        """Load a card's behavioral profile hash from Redis as a plain dict."""
        raw = await self._redis.hgetall(key)
        return {
            (k.decode() if isinstance(k, bytes) else k): (v.decode() if isinstance(v, bytes) else v)
            for k, v in raw.items()
        }

    async def _update_profile(
        self,
        key: str,
        tx: TransactionCreate,
        profile: dict,
        known_devices: list[str],
        known_countries: list[str],
    ) -> None:
        """Update the behavioral profile in Redis after scoring.

        Uses Welford's online algorithm to update the rolling mean and
        standard deviation without storing all historical values.
        """
        amount_f = float(tx.amount)
        tx_count_total = int(profile.get("tx_count_total", 0) or 0) + 1

        old_avg = float(profile.get("avg_amount_overall", 0) or 0)
        old_m2 = float(profile.get("m2_amount", 0) or 0)
        new_avg = old_avg + (amount_f - old_avg) / tx_count_total
        new_m2 = old_m2 + (amount_f - old_avg) * (amount_f - new_avg)
        new_stddev = math.sqrt(new_m2 / tx_count_total) if tx_count_total > 1 else 0.0

        tx_count_7d = int(profile.get("tx_count_7d", 0) or 0) + 1

        if tx.device_fingerprint not in known_devices:
            known_devices.append(tx.device_fingerprint)
        known_devices = known_devices[-10:]

        if tx.country_code not in known_countries:
            known_countries.append(tx.country_code)
        known_countries = known_countries[-20:]

        mcc_key = f"avg_amount_{tx.merchant_category_code}"
        old_mcc_avg = float(profile.get(mcc_key, 0) or 0)
        mcc_count = int(profile.get(f"count_{tx.merchant_category_code}", 0) or 0) + 1
        new_mcc_avg = old_mcc_avg + (amount_f - old_mcc_avg) / mcc_count

        updates = {
            "tx_count_total": tx_count_total,
            "tx_count_7d": tx_count_7d,
            "avg_amount_overall": round(new_avg, 6),
            "stddev_amount": round(new_stddev, 6),
            "m2_amount": round(new_m2, 6),
            "known_devices": json.dumps(known_devices),
            "known_countries": json.dumps(known_countries),
            "last_tx_country": tx.country_code,
            mcc_key: round(new_mcc_avg, 6),
            f"count_{tx.merchant_category_code}": mcc_count,
            "last_tx_timestamp": datetime.now(timezone.utc).isoformat(),
        }

        if tx.latitude is not None:
            updates["last_tx_lat"] = tx.latitude
        if tx.longitude is not None:
            updates["last_tx_lon"] = tx.longitude

        hset_pipe = self._redis.pipeline()
        for field, value in updates.items():
            hset_pipe.hset(key, field, value)
        await hset_pipe.execute()
        await self._redis.expire(key, PROFILE_TTL)

        v1h_key = f"sentinelpay:velocity:{tx.card_last4}:1h"
        v24h_key = f"sentinelpay:velocity:{tx.card_last4}:24h"
        pipe = self._redis.pipeline()
        pipe.incr(v1h_key)
        pipe.expire(v1h_key, 3600)
        pipe.incr(v24h_key)
        pipe.expire(v24h_key, 86400)
        await pipe.execute()
