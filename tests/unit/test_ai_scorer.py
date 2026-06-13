"""Unit tests for AIScorer — response parsing and Anthropic API error fallback."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import anthropic

from app.services.ai_scorer import AIScorer, _FALLBACK
from app.services.rule_engine import RuleResult
from app.services.behavioral_profiler import BehavioralResult


def _make_message(text: str):
    """Build a minimal mock Anthropic message response object."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@pytest.fixture
def scorer():
    return AIScorer()


@pytest.fixture
def rule_pass():
    return RuleResult(result="PASS", reasons=[])


@pytest.fixture
def behavioral_low():
    return BehavioralResult(behavioral_score=0.10, anomalies=[])


class TestParseResponse:
    def test_valid_json_parsed_correctly(self, scorer):
        """A well-formed Claude JSON response populates all AIResult fields."""
        raw = json.dumps({
            "risk_score": 25,
            "risk_level": "LOW",
            "explanation": "Transaction looks normal.",
            "recommended_action": "APPROVE",
        })
        result = scorer._parse_response(raw)
        assert result.risk_score == 25
        assert result.risk_level == "LOW"
        assert result.recommended_action == "APPROVE"
        assert result.skipped is False

    def test_markdown_fenced_json_parsed_correctly(self, scorer):
        """A Claude response wrapped in ```json ... ``` fences is parsed without falling back."""
        inner = json.dumps({
            "risk_score": 72,
            "risk_level": "HIGH",
            "explanation": "Suspicious pattern detected.",
            "recommended_action": "REVIEW",
        })
        raw = f"```json\n{inner}\n```"
        result = scorer._parse_response(raw)
        assert result.risk_score == 72
        assert result.risk_level == "HIGH"
        assert result.skipped is False

    def test_invalid_json_returns_fallback(self, scorer):
        """Unparseable output must fall back to the medium-risk result."""
        result = scorer._parse_response("not json at all")
        assert result.risk_score == _FALLBACK.risk_score
        assert result.risk_level == _FALLBACK.risk_level

    def test_missing_field_returns_fallback(self, scorer):
        """JSON missing a required key must trigger the fallback."""
        raw = json.dumps({"risk_score": 10})  # missing risk_level, etc.
        result = scorer._parse_response(raw)
        assert result.risk_level == _FALLBACK.risk_level


class TestAPICallAndFallback:
    async def test_successful_api_call_returns_result(self, scorer, sample_tx, rule_pass, behavioral_low):
        """A successful Anthropic API response is parsed into a valid AIResult."""
        mock_response = _make_message(json.dumps({
            "risk_score": 20,
            "risk_level": "LOW",
            "explanation": "No suspicious activity.",
            "recommended_action": "APPROVE",
        }))
        with patch.object(scorer._client.messages, "create", new=AsyncMock(return_value=mock_response)):
            result = await scorer.score(sample_tx, rule_pass, behavioral_low)
        assert result.risk_score == 20
        assert result.risk_level == "LOW"
        assert result.skipped is False

    async def test_connection_error_returns_fallback(self, scorer, sample_tx, rule_pass, behavioral_low):
        """An Anthropic connection error must return the fallback result, not raise."""
        with patch.object(
            scorer._client.messages,
            "create",
            side_effect=anthropic.APIConnectionError(request=MagicMock()),
        ):
            result = await scorer.score(sample_tx, rule_pass, behavioral_low)
        assert result.risk_score == _FALLBACK.risk_score
        assert result.risk_level == "MEDIUM"

    async def test_api_status_error_returns_fallback(self, scorer, sample_tx, rule_pass, behavioral_low):
        """An Anthropic API status error must return the fallback result, not raise."""
        with patch.object(
            scorer._client.messages,
            "create",
            side_effect=anthropic.APIStatusError(
                "error", response=MagicMock(status_code=500), body={}
            ),
        ):
            result = await scorer.score(sample_tx, rule_pass, behavioral_low)
        assert result.risk_level == "MEDIUM"
