"""Alertas por Telegram. Si faltan TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID, no envía nada.

Un fallo al enviar nunca detiene el bot: las alertas también quedan en la tabla `alerts`.
Los mensajes van en HTML de Telegram: un título, una tabla alineada en monoespaciado y un pie con
la instancia, la hora UTC y el enlace al dashboard.
"""

import html
import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

from dotenv import load_dotenv

log = logging.getLogger("tradebot.notify")
API = "https://api.telegram.org/bot{token}/sendMessage"
DASHBOARD = "https://web-pi-inky-0cgra45qzm.vercel.app"
LEVELS = {"info": ("ℹ️", "Info"), "warning": ("⚠️", "Aviso"), "critical": ("🚨", "Crítico")}
MONTHS = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


@dataclass(frozen=True)
class Card:
    """Mensaje con estructura: título, filas etiqueta/valor y una nota opcional en cursiva."""
    icon: str
    title: str
    rows: tuple[tuple[str, str], ...] = ()
    note: str = ""


def price(value: float) -> str:
    return f"{value:,.2f}" if abs(value) >= 100 else f"{value:,.4f}"


def signed(value: float, unit: str = "USDT") -> str:
    return f"{value:+,.2f} {unit}"


def coin(symbol: str) -> str:
    return symbol.split("/")[0]


def render(level: str, message: str, card: Card | None, source: str, now: datetime) -> str:
    if card is None:
        icon, label = LEVELS.get(level, ("", level))
        card = Card(icon, label, note=message)
    lines = [f"{card.icon} <b>{html.escape(card.title)}</b>"]
    if card.rows:
        width = max(len(label) for label, _ in card.rows)
        table = "\n".join(f"{label.ljust(width)}  {value}" for label, value in card.rows)
        lines.append(f"<pre>{html.escape(table)}</pre>")
    if card.note:
        lines.append(html.escape(card.note))
    stamp = f"{now.day:02d} {MONTHS[now.month - 1]} {now:%H:%M} UTC"
    footer = " · ".join(p for p in (html.escape(source), stamp) if p)
    lines.append(f'<i>{footer}</i> · <a href="{DASHBOARD}">dashboard</a>')
    return "\n".join(lines)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str, source: str = ""):
        self.token = token
        self.chat_id = chat_id
        self.source = source

    def send(self, level: str, message: str, card: Card | None = None) -> bool:
        text = render(level, message, card, self.source, datetime.now(UTC))
        try:
            try:
                return self._post({"text": text, "parse_mode": "HTML", "disable_web_page_preview": True})
            except urllib.error.HTTPError as exc:
                if exc.code != 400:
                    raise
                # Telegram rechazó el HTML: la alerta sale igual, en texto plano.
                icon, _ = LEVELS.get(level, ("", ""))
                return self._post({"text": f"{icon} [{self.source}] {message}"})
        except OSError as exc:
            # No se registra la URL: contiene el token.
            log.warning("no se pudo enviar la alerta a Telegram (%s)", type(exc).__name__)
            return False

    def _post(self, payload: dict) -> bool:
        body = json.dumps({"chat_id": self.chat_id, **payload}).encode()
        request = urllib.request.Request(API.format(token=self.token), data=body,
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status == 200


class NullNotifier:
    def send(self, level: str, message: str, card: Card | None = None) -> bool:
        return False


def create_notifier(source: str = "") -> TelegramNotifier | NullNotifier:
    load_dotenv()
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return NullNotifier()
    return TelegramNotifier(token, chat_id, source)


def failure_card(what: str, exc: Exception) -> Card:
    return Card("🚨", f"Falló {what}", (("Error", type(exc).__name__),), str(exc)[:300])
