"""Analista IA que usa la suscripción de Claude a través de Claude Code en modo no interactivo."""

import json
import shutil
import subprocess
from pathlib import Path

from tradebot.ai.base import (
    AIResponseError,
    QuotaExceededError,
    Review,
    ReviewDecision,
    parse_decision,
)

__all__ = ["AIResponseError", "ClaudeCLIAnalyst", "QuotaExceededError", "Review", "ReviewDecision", "parse_decision"]


# Instalación nativa de Claude Code; sirve cuando el proceso arrancó con un PATH sin esa carpeta.
DEFAULT_INSTALL = Path.home() / ".local" / "bin" / "claude.exe"


def find_claude() -> str:
    found = shutil.which("claude")
    if found:
        return found
    return str(DEFAULT_INSTALL) if DEFAULT_INSTALL.exists() else "claude"


class ClaudeCLIAnalyst:
    def __init__(self, timeout_seconds: int, executable: str | None = None):
        self.timeout_seconds = timeout_seconds
        self.executable = executable or find_claude()

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
            # El CLI reporta aparte los tokens servidos desde caché; el total de entrada es la suma.
            input_tokens=sum(usage.get(k, 0) for k in
                             ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")),
            output_tokens=usage.get("output_tokens", 0),
            duration_ms=envelope.get("duration_ms", 0),
        )

    def _run(self, prompt: str, model: str) -> dict:
        # --tools "" deja a Claude sin herramientas: solo razona sobre los datos que le pasamos,
        # así cada revisión gasta una sola respuesta de la cuota.
        command = [self.executable, "-p", prompt, "--output-format", "json", "--model", model, "--tools", ""]
        try:
            # encoding explícito: en Windows el default es la página de códigos del sistema y daña los acentos.
            completed = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=self.timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AIResponseError(f"Claude CLI no respondió en {self.timeout_seconds} s") from exc
        except OSError as exc:
            raise AIResponseError(f"no se pudo ejecutar Claude CLI ({self.executable}): {exc}") from exc

        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            detail = (completed.stderr or completed.stdout).strip()[:500]
            raise AIResponseError(f"Salida del CLI no es JSON (código {completed.returncode}): {detail}") from exc
