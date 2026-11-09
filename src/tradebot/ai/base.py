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
        return ReviewDecision.model_validate_json(match.group(0))
    except ValidationError as exc:
        raise AIResponseError(f"JSON de la IA no cumple el esquema: {exc}") from exc
