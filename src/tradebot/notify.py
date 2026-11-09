"""Alertas por Telegram. Si faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID, no envía nada.

Un fallo al enviar nunca detiene el bot: las alertas también quedan en la tabla `alerts`.
"""

import json
import logging
import os
import urllib.request

from dotenv import load_dotenv

log = logging.getLogger("tradebot.notify")
API = "https://api.telegram.org/bot{token}/sendMessage"
ICONS = {"info": "ℹ️", "warning": "⚠️", "critical": "🚨"}


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, prefix: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.prefix = prefix

    def send(self, level: str, message: str) -> bool:
        body = json.dumps({"chat_id": self.chat_id, "text": f"{ICONS.get(level, '')} {self.prefix}{message}"}).encode()
        request = urllib.request.Request(API.format(token=self.token), data=body,
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status == 200
        except OSError as exc:
            # No se registra la URL: contiene el token.
            log.warning("no se pudo enviar la alerta a Telegram (%s)", type(exc).__name__)
            return False


class NullNotifier:
    def send(self, level: str, message: str) -> bool:
        return False


def create_notifier(prefix: str = "") -> TelegramNotifier | NullNotifier:
    load_dotenv()
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return NullNotifier()
    return TelegramNotifier(token, chat_id, prefix)
