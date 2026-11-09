# tradebot

Bot de trading de cripto que opera **solo en papel** (testnet), con un analista de IA (Claude) que revisa cada señal antes de operar. El objetivo es medir con honestidad si el bot, después de comisiones, le gana a comprar y mantener BTC.

> Proyecto experimental y educativo. No es consejo de inversión y no está pensado para operar con dinero real.

## Cómo funciona

Datos de mercado → indicadores → señal y filtros → analista IA → motor de riesgo → ejecución → posiciones → aprendizaje. Claude solo puede aprobar, reducir o vetar una señal; el riesgo y la ejecución son código.

La IA usa la suscripción de Claude a través de Claude Code en modo no interactivo (`claude -p`), así que comparte los límites de uso del plan. Si se agota la cuota, el bot sigue con la estrategia base.

## Estado

- [x] Fase 0: configuración, esquema de base de datos, conexión a testnet y a Claude
- [ ] Fase 1: ingesta de datos
- [ ] Fase 2: estrategia base y backtest
- [ ] Fase 3: analista IA
- [ ] Fase 4: riesgo y ejecución
- [ ] Fase 5: paper trading y dashboard (Streamlit)

## Puesta en marcha

Requisitos: Python 3.12+, [Claude Code](https://docs.claude.com/en/docs/claude-code) con sesión iniciada en tu plan, un proyecto de Supabase y una cuenta de testnet en Bybit o Binance.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # completa llaves de testnet y DATABASE_URL
```

1. En Supabase, abre el SQL Editor y ejecuta `sql/001_schema.sql`.
2. Crea llaves de API en la testnet del exchange (sin permiso de retiro) y ponlas en `.env`.
3. Revisa `config/settings.toml` (exchange, mercado, monedas).
4. Corre el chequeo:

```bash
python -m tradebot.check
```

Debe mostrar `OK` en `claude`, `exchange` y `supabase`.

## Tests

```bash
pytest
```

## Estructura

```
config/settings.toml        parámetros del bot, IA y riesgo
sql/001_schema.sql          tablas en Supabase
src/tradebot/config.py      carga de configuración y secretos
src/tradebot/exchange.py    cliente ccxt (siempre en testnet)
src/tradebot/ai/claude_cli.py  analista IA vía claude -p
src/tradebot/check.py       chequeo de conexiones
tests/
```
