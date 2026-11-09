from tradebot.ai.base import AIAnalyst, AIResponseError, QuotaExceededError, Review, ReviewDecision
from tradebot.ai.claude_cli import ClaudeCLIAnalyst
from tradebot.config import AISettings


def create_analyst(settings: AISettings) -> AIAnalyst:
    if settings.provider == "cli":
        return ClaudeCLIAnalyst(timeout_seconds=settings.timeout_seconds)
    raise ValueError(f"proveedor de IA no soportado: {settings.provider}")


__all__ = [
    "AIAnalyst", "AIResponseError", "ClaudeCLIAnalyst", "QuotaExceededError",
    "Review", "ReviewDecision", "create_analyst",
]
