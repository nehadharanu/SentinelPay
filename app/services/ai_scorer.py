import json
import logging
from dataclasses import dataclass, field
from typing import Literal

import anthropic

from app.config import settings
from app.schemas.transaction import TransactionCreate
from app.services.behavioral_profiler import BehavioralResult
from app.services.rule_engine import RuleResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a payment fraud analyst. You will receive a JSON object containing:
- transaction details
- layer1_reasons: list of rule-engine flags (empty if none)
- layer2_behavioral_score: float 0.0–1.0 (higher = more anomalous)
- layer2_anomalies: list of behavioral anomaly codes

Respond ONLY with a valid JSON object — no prose, no markdown, no explanation outside the JSON.
The JSON must have exactly these four keys:
{
  "risk_score": <integer 0-100>,
  "risk_level": <"LOW" | "MEDIUM" | "HIGH" | "CRITICAL">,
  "explanation": "<one or two sentences>",
  "recommended_action": <"APPROVE" | "FLAG" | "REVIEW" | "BLOCK">
}

risk_score thresholds: LOW=0-39, MEDIUM=40-59, HIGH=60-79, CRITICAL=80-100."""


@dataclass
class AIResult:
    """Output of Layer 3 Claude AI risk scoring."""

    risk_score: int
    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    explanation: str
    recommended_action: Literal["APPROVE", "FLAG", "REVIEW", "BLOCK"]
    skipped: bool = False


_FALLBACK = AIResult(
    risk_score=50,
    risk_level="MEDIUM",
    explanation="AI scorer unavailable; fallback medium risk applied.",
    recommended_action="REVIEW",
    skipped=False,
)


class AIScorer:
    """Layer 3: Claude AI risk scoring via the Anthropic API.

    Sends transaction context and prior layer results to Claude and
    parses a structured JSON risk assessment in return.
    """

    def __init__(self):
        """Initialise the Anthropic client with the configured API key."""
        self._client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)

    async def score(
        self,
        tx: TransactionCreate,
        rule_result: RuleResult,
        behavioral_result: BehavioralResult,
    ) -> AIResult:
        """Call the Anthropic API and return a structured AIResult.

        If the API is unreachable or returns unparseable output, a fallback
        MEDIUM-risk result is returned instead of raising.
        """
        payload = {
            "transaction": {
                "amount": str(tx.amount),
                "currency": tx.currency,
                "card_last4": tx.card_last4,
                "card_bin": tx.card_bin,
                "merchant_category_code": tx.merchant_category_code,
                "merchant_name": tx.merchant_name,
                "ip_address": tx.ip_address,
                "country_code": tx.country_code,
                "city": tx.city,
                "device_fingerprint": tx.device_fingerprint,
            },
            "layer1_reasons": rule_result.reasons,
            "layer2_behavioral_score": round(behavioral_result.behavioral_score, 3),
            "layer2_anomalies": behavioral_result.anomalies,
        }

        try:
            message = await self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                temperature=0,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": json.dumps(payload)}],
            )
            raw = message.content[0].text.strip()
            return self._parse_response(raw)
        except anthropic.APIConnectionError as exc:
            logger.error("Anthropic API connection error: %s", exc)
            return _FALLBACK
        except anthropic.APIStatusError as exc:
            logger.error("Anthropic API status error %s: %s", exc.status_code, exc.message)
            return _FALLBACK
        except Exception as exc:
            logger.error("Unexpected AI scorer error: %s", exc)
            return _FALLBACK

    def _parse_response(self, raw: str) -> AIResult:
        """Parse the Claude JSON response into an AIResult.

        Falls back to a medium-risk result if parsing fails.
        """
        try:
            text = raw.strip().removeprefix("```json").removesuffix("```").strip()
            data = json.loads(text)
            return AIResult(
                risk_score=int(data["risk_score"]),
                risk_level=data["risk_level"],
                explanation=data["explanation"],
                recommended_action=data["recommended_action"],
                skipped=False,
            )
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.error("Failed to parse AI scorer response: %s | raw: %s", exc, raw[:200])
            return _FALLBACK
