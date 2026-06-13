"""Unit tests for FraudEngine._decide — the final decision matrix."""

from unittest.mock import AsyncMock

import pytest

from app.services.fraud_engine import FraudEngine
from app.services.rule_engine import RuleResult
from app.services.behavioral_profiler import BehavioralResult
from app.services.ai_scorer import AIResult


def _engine(mock_rule, mock_behavioral, mock_ai):
    engine = FraudEngine(
        rule_engine=mock_rule,
        behavioral_profiler=mock_behavioral,
        ai_scorer=mock_ai,
    )
    return engine


def _decide(rule_result, behavioral_result, ai_result):
    """Directly exercise the decision matrix without running the pipeline."""
    engine = FraudEngine(
        rule_engine=AsyncMock(),
        behavioral_profiler=AsyncMock(),
        ai_scorer=AsyncMock(),
    )
    return engine._decide(rule_result, behavioral_result, ai_result)


class TestDecisionMatrix:
    def test_critical_ai_risk_returns_block(self, rule_pass, behavioral_low, ai_critical):
        """Any CRITICAL AI risk level must produce BLOCK regardless of other layers."""
        assert _decide(rule_pass, behavioral_low, ai_critical) == "BLOCK"

    def test_flag_with_high_ai_returns_block(self, rule_flag, behavioral_mid, ai_high):
        """FLAG rule result combined with HIGH AI risk must escalate to BLOCK."""
        assert _decide(rule_flag, behavioral_mid, ai_high) == "BLOCK"

    def test_high_behavioral_score_returns_review(self, rule_pass, behavioral_high, ai_medium):
        """Behavioral score > 0.55 must produce REVIEW."""
        assert _decide(rule_pass, behavioral_high, ai_medium) == "REVIEW"

    def test_mid_behavioral_high_ai_returns_review(self, rule_pass, behavioral_mid, ai_high):
        """Behavioral 0.25–0.55 combined with HIGH AI must produce REVIEW."""
        assert _decide(rule_pass, behavioral_mid, ai_high) == "REVIEW"

    def test_mid_behavioral_medium_ai_returns_flag(self, rule_pass, behavioral_mid, ai_medium):
        """Behavioral 0.25–0.55 combined with MEDIUM AI must produce FLAG."""
        assert _decide(rule_pass, behavioral_mid, ai_medium) == "FLAG"

    def test_low_behavioral_low_ai_returns_approve(self, rule_pass, behavioral_low, ai_low):
        """Behavioral < 0.25 combined with LOW AI must produce APPROVE."""
        assert _decide(rule_pass, behavioral_low, ai_low) == "APPROVE"

    def test_low_behavioral_medium_ai_returns_flag(self, rule_pass, behavioral_low, ai_medium):
        """Behavioral < 0.25 combined with MEDIUM AI must produce FLAG."""
        assert _decide(rule_pass, behavioral_low, ai_medium) == "FLAG"


class TestAnalyzePipelineShortCircuit:
    async def test_layer1_block_skips_layers_2_and_3(self, sample_tx, rule_block, mock_redis):
        """When Layer 1 returns BLOCK the behavioral profiler and AI scorer are never called."""
        mock_rule_engine = AsyncMock()
        mock_rule_engine.evaluate = AsyncMock(return_value=rule_block)

        mock_behavioral = AsyncMock()
        mock_ai = AsyncMock()

        engine = FraudEngine(mock_rule_engine, mock_behavioral, mock_ai)
        result = await engine.analyze(sample_tx)

        assert result.final_decision == "BLOCK"
        mock_behavioral.score.assert_not_called()
        mock_ai.score.assert_not_called()

    async def test_layer1_pass_runs_all_layers(self, sample_tx, rule_pass, behavioral_low, ai_low):
        """When Layer 1 passes, all three layers execute and APPROVE is returned."""
        mock_rule_engine = AsyncMock()
        mock_rule_engine.evaluate = AsyncMock(return_value=rule_pass)

        mock_behavioral = AsyncMock()
        mock_behavioral.score = AsyncMock(return_value=behavioral_low)

        mock_ai = AsyncMock()
        mock_ai.score = AsyncMock(return_value=ai_low)

        engine = FraudEngine(mock_rule_engine, mock_behavioral, mock_ai)
        result = await engine.analyze(sample_tx)

        assert result.final_decision == "APPROVE"
        mock_behavioral.score.assert_called_once()
        mock_ai.score.assert_called_once()
