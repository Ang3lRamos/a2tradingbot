"""Revisión de una señal: control de cuota, llamada a la IA, registro y tamaño resultante."""

from dataclasses import dataclass

import psycopg

from tradebot import db
from tradebot.ai.base import AIAnalyst, AIResponseError, QuotaExceededError
from tradebot.config import AISettings

UNREVIEWED = "sin_revision"


@dataclass(frozen=True)
class ReviewOutcome:
    decision: str  # approve | reduce | veto | sin_revision
    size_multiplier: float  # nunca mayor que 1: la IA solo puede reducir
    error: str | None = None
    quota_exhausted: bool = False


def size_for(decision: str, multiplier: float) -> float:
    if decision == "approve":
        return 1.0
    if decision == "reduce":
        return min(max(multiplier, 0.1), 0.9)
    return 0.0


def _fallback(settings: AISettings, error: str, quota_exhausted: bool) -> ReviewOutcome:
    size = 1.0 if settings.fallback == "base" else 0.0
    return ReviewOutcome(UNREVIEWED, size, error, quota_exhausted)


def review_signal(conn: psycopg.Connection, analyst: AIAnalyst, settings: AISettings, quota_instance: str,
                  signal_id: int, prompt: str) -> ReviewOutcome:
    model = settings.decision_model
    if not db.reserve_ai_call(conn, quota_instance, settings.daily_call_limit):
        # No se registra: la señal queda pendiente y se puede revisar otro día.
        return _fallback(settings, f"tope propio de {settings.daily_call_limit} llamadas diarias alcanzado", True)
    try:
        review = analyst.review(prompt, model)
    except (QuotaExceededError, AIResponseError) as exc:
        db.save_ai_review(conn, signal_id, model, prompt, None, None, str(exc)[:1000], None, None, None)
        return _fallback(settings, str(exc), isinstance(exc, QuotaExceededError))

    decision = review.decision
    db.save_ai_review(conn, signal_id, review.model, prompt, decision.model_dump(), decision.decision, None,
                      review.input_tokens, review.output_tokens, review.duration_ms)
    return ReviewOutcome(decision.decision, size_for(decision.decision, decision.size_multiplier))
