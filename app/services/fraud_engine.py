import logging
import time
from dataclasses import dataclass

from app.schemas.transaction import TransactionCreate
from app.services.ai_scorer import AIResult, AIScorer
from app.services.behavioral_profiler import BehavioralProfiler, BehavioralResult
from app.services.rule_engine import RuleEngine, RuleResult

logger = logging.getLogger(__name__)


@dataclass
class FraudDecisionResult:
    """Aggregated output of the full 3-layer fraud detection pipeline."""

    final_decision: str
    recommended_action: str
    processing_ms: int
    rule_result: RuleResult
    behavioral_result: BehavioralResult
    ai_result: AIResult | None


class FraudEngine:
    """Orchestrates the 3-layer fraud detection pipeline.

    Calls the rule engine, behavioral profiler, and AI scorer in order,
    short-circuiting to BLOCK if Layer 1 fires a hard block.
    """

    def __init__(
        self,
        rule_engine: RuleEngine,
        behavioral_profiler: BehavioralProfiler,
        ai_scorer: AIScorer,
    ):
        """Initialise with pre-constructed service instances."""
        self._rule_engine = rule_engine
        self._behavioral_profiler = behavioral_profiler
        self._ai_scorer = ai_scorer

    async def analyze(self, tx: TransactionCreate) -> FraudDecisionResult:
        """Run the full 3-layer pipeline against a transaction and return the fraud decision.

        Short-circuits after Layer 1 if result is BLOCK. Otherwise all
        three layers execute and the final decision matrix is applied.
        """
        start_ms = time.monotonic()

        rule_result = await self._rule_engine.evaluate(tx)

        if rule_result.result == "BLOCK":
            processing_ms = int((time.monotonic() - start_ms) * 1000)
            skipped_behavioral = BehavioralResult(behavioral_score=0.0, anomalies=[])
            skipped_ai = AIResult(
                risk_score=0,
                risk_level="CRITICAL",
                explanation="Blocked by rule engine; AI scoring skipped.",
                recommended_action="BLOCK",
                skipped=True,
            )
            return FraudDecisionResult(
                final_decision="BLOCK",
                recommended_action="BLOCK",
                processing_ms=processing_ms,
                rule_result=rule_result,
                behavioral_result=skipped_behavioral,
                ai_result=skipped_ai,
            )

        behavioral_result = await self._behavioral_profiler.score(tx)
        ai_result = await self._ai_scorer.score(tx, rule_result, behavioral_result)

        final_decision = self._decide(rule_result, behavioral_result, ai_result)
        processing_ms = int((time.monotonic() - start_ms) * 1000)

        return FraudDecisionResult(
            final_decision=final_decision,
            recommended_action=final_decision,
            processing_ms=processing_ms,
            rule_result=rule_result,
            behavioral_result=behavioral_result,
            ai_result=ai_result,
        )

    def _decide(
        self,
        rule_result: RuleResult,
        behavioral_result: BehavioralResult,
        ai_result: AIResult,
    ) -> str:
        """Apply the final decision matrix and return one of APPROVE/FLAG/REVIEW/BLOCK.

        Decision matrix (from ARCHITECTURE.md):
        - Any CRITICAL AI risk level → BLOCK
        - FLAG + (HIGH or CRITICAL) AI risk → BLOCK
        - behavioral_score > 0.55 → REVIEW
        - behavioral_score 0.25–0.55 + HIGH AI risk → REVIEW
        - behavioral_score 0.25–0.55 + LOW/MEDIUM AI risk → FLAG
        - behavioral_score < 0.25 + MEDIUM AI risk → FLAG
        - behavioral_score < 0.25 + LOW AI risk → APPROVE
        """
        score = behavioral_result.behavioral_score
        risk_level = ai_result.risk_level

        if risk_level == "CRITICAL":
            return "BLOCK"

        if rule_result.result == "FLAG" and risk_level in ("HIGH", "CRITICAL"):
            return "BLOCK"

        if score > 0.55:
            return "REVIEW"

        if 0.25 <= score <= 0.55:
            if risk_level == "HIGH":
                return "REVIEW"
            return "FLAG"

        if score < 0.25:
            if risk_level == "LOW":
                return "APPROVE"
            return "FLAG"

        return "FLAG"
