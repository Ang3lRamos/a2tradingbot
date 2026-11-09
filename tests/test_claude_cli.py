import json
import subprocess

import pytest

from tradebot.ai.claude_cli import (
    AIResponseError,
    ClaudeCLIAnalyst,
    QuotaExceededError,
    parse_decision,
)

VALID = '{"decision": "reduce", "confidence": 0.6, "size_multiplier": 0.5, "reasons": ["funding alto"]}'


def fake_cli(monkeypatch, stdout: str, returncode: int = 0):
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", run)


def envelope(result: str, is_error: bool = False) -> str:
    return json.dumps({
        "is_error": is_error,
        "result": result,
        "duration_ms": 1200,
        "usage": {"input_tokens": 300, "output_tokens": 40},
    })


def test_parse_decision_accepts_code_fence():
    decision = parse_decision(f"```json\n{VALID}\n```")
    assert decision.decision == "reduce"
    assert decision.risk_flags == []


@pytest.mark.parametrize("text", [
    "no tengo opinión",
    '{"decision": "comprar", "confidence": 0.6, "size_multiplier": 0.5, "reasons": []}',
    '{"decision": "approve", "confidence": 1.4, "size_multiplier": 0.5, "reasons": []}',
])
def test_parse_decision_rejects_invalid(text):
    with pytest.raises(AIResponseError):
        parse_decision(text)


def test_review_returns_usage(monkeypatch):
    fake_cli(monkeypatch, envelope(VALID))
    review = ClaudeCLIAnalyst(timeout_seconds=5).review("prompt", model="haiku")
    assert review.decision.size_multiplier == 0.5
    assert (review.input_tokens, review.output_tokens, review.duration_ms) == (300, 40, 1200)


def test_review_detects_quota(monkeypatch):
    fake_cli(monkeypatch, envelope("Claude AI usage limit reached", is_error=True))
    with pytest.raises(QuotaExceededError):
        ClaudeCLIAnalyst(timeout_seconds=5).review("prompt", model="haiku")


def test_review_reports_cli_error(monkeypatch):
    fake_cli(monkeypatch, envelope("Authentication error", is_error=True))
    with pytest.raises(AIResponseError, match="Authentication"):
        ClaudeCLIAnalyst(timeout_seconds=5).review("prompt", model="haiku")


def test_review_handles_non_json_output(monkeypatch):
    fake_cli(monkeypatch, "command not found", returncode=127)
    with pytest.raises(AIResponseError, match="127"):
        ClaudeCLIAnalyst(timeout_seconds=5).review("prompt", model="haiku")
