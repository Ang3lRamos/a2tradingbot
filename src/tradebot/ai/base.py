"""Contrato común de los analistas IA: lo que reciben, lo que devuelven y cómo fallan.

El resto del bot depende solo de `AIAnalyst`, así cambiar de CLI a API es una línea en settings.toml.
"""

import re
from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field, ValidationError

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reduce", "veto"]
    confidence: float = Field(ge=0, le=1)
    size_multiplier: float = Field(ge=0, le=1)
    reasons: list[str]
    risk_flags: list[str] = []
    score: int | None = Field(default=None, ge=0, le=100)  # prompt v2: puntaje 0-100


class ScoreReply(BaseModel):
    """Respuesta del prompt v2: un puntaje en vez de una decisión."""
    score: int = Field(ge=0, le=100)
    reasons: list[str]
    risk_flags: list[str] = []


def decision_from_score(reply: ScoreReply) -> ReviewDecision:
    """El tamaño es puntaje/100. Debajo de 20 se veta y desde 80 se opera completo."""
    size = reply.score / 100
    decision = "veto" if reply.score < 20 else "approve" if reply.score >= 80 else "reduce"
    return ReviewDecision(decision=decision, confidence=size, reasons=reply.reasons, risk_flags=reply.risk_flags,
                          size_multiplier=1.0 if decision == "approve" else 0.0 if decision == "veto" else size,
                          score=reply.score)


@dataclass(frozen=True)
class Review:
    decision: ReviewDecision
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int


class QuotaExceededError(RuntimeError):
    """El plan llegó a su límite de uso; el bot debe seguir sin IA hasta que se renueve."""


class AIResponseError(RuntimeError):
    """La IA falló o la respuesta no cumple el formato esperado; la señal se trata como vetada."""


class AIAnalyst(Protocol):
    def review(self, prompt: str, model: str) -> Review:
        """Revisa una señal. Lanza QuotaExceededError o AIResponseError si no hay decisión válida."""
        ...


def parse_decision(text: str) -> ReviewDecision:
    match = _JSON_OBJECT.search(text)
    if not match:
        raise AIResponseError(f"La respuesta no contiene un objeto JSON: {text[:200]}")
    try:
        if '"decision"' not in match.group(0) and '"score"' in match.group(0):
            return decision_from_score(ScoreReply.model_validate_json(match.group(0)))
        return ReviewDecision.model_validate_json(match.group(0))
    except ValidationError as exc:
        raise AIResponseError(f"JSON de la IA no cumple el esquema: {exc}") from exc
