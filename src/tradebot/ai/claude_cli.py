"""Analista IA que usa la suscripción de Claude a través de Claude Code en modo no interactivo."""

import json
import subprocess

from tradebot.ai.base import (
    AIResponseError,
    QuotaExceededError,
    Review,
    ReviewDecision,
    parse_decision,
)

__all__ = ["AIResponseError", "ClaudeCLIAnalyst", "QuotaExceededError", "Review", "ReviewDecision", "parse_decision"]


class ClaudeCLIAnalyst:
    def __init__(self, timeout_seconds: int, executable: str = "claude"):
        self.timeout_seconds = timeout_seconds
        self.executable = executable

    def review(self, prompt: str, model: str) -> Review:
        envelope = self._run(prompt, model)
        if envelope.get("is_error"):
            message = str(envelope.get("result", ""))
            if "limit" in message.lower():
                raise QuotaExceededError(message)
            raise AIResponseError(f"Claude CLI devolvió un error: {message}")

        usage = envelope.get("usage", {})
        return Review(
            decision=parse_decision(envelope.get("result", "")),
            model=model,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=envelope.get("duration_ms", 0),
        )

    def _run(self, prompt: str, model: str) -> dict:
        # --tools "" deja a Claude sin herramientas: solo razona sobre los datos que le pasamos,
        # así cada revisión gasta una sola respuesta de la cuota.
        command = [self.executable, "-p", prompt, "--output-format", "json", "--model", model, "--tools", ""]
        try:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=self.timeout_seconds, check=False
            )
        except subprocess.TimeoutExpired as exc:
            raise AIResponseError(f"Claude CLI no respondió en {self.timeout_seconds} s") from exc

        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            detail = (completed.stderr or completed.stdout).strip()[:500]
            raise AIResponseError(f"Salida del CLI no es JSON (código {completed.returncode}): {detail}") from exc
