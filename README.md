# tradebot

Bot de trading de cripto que opera **solo en papel** (testnet), con un analista de IA (Claude) que revisa cada señal antes de operar. El objetivo es medir con honestidad si el bot, después de comisiones, le gana a comprar y mantener BTC.

> Proyecto experimental y educativo. No es consejo de inversión y no está pensado para operar con dinero real.

## Cómo funciona

Datos de mercado → indicadores → señal y filtros → analista IA → motor de riesgo → ejecución → posiciones → aprendizaje. Claude solo puede aprobar, reducir o vetar una señal; el riesgo y la ejecución son código.

La IA usa la suscripción de Claude a través de Claude Code en modo no interactivo (`claude -p`), así que comparte los límites de uso del plan. Si se agota la cuota, el bot sigue con la estrategia base.

## Estado

- [x] Fase 0: configuración, esquema de base de datos, conexión a testnet y a Claude
- [x] Fase 1: ingesta de datos
- [ ] Fase 2: estrategia base y backtest (sin ventaja out-of-sample; ver docs/resultados_fase2.md)
- [ ] Fase 3: analista IA (en evaluación: python -m tradebot.ai_eval)
- [ ] Fase 4: riesgo y ejecución (código listo; falta probar órdenes reales en la cuenta demo)
- [ ] Fase 5: paper trading y dashboard (Streamlit)

## Puesta en marcha

Requisitos: Python 3.12+, [Claude Code](https://docs.claude.com/en/docs/claude-code) con sesión iniciada en tu plan, un proyecto de Supabase y una cuenta en Binance Demo Trading (demo.binance.com) o en la testnet de Bybit.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # completa llaves de testnet y DATABASE_URL
```

1. En Supabase, abre el SQL Editor y ejecuta `sql/001_schema.sql`.
2. Crea llaves de API en Binance Demo Trading o en la testnet de Bybit (sin permiso de retiro) y ponlas en `.env`.
3. Revisa `config/settings.toml` (exchange, mercado, monedas).
4. Corre el chequeo:

```bash
python -m tradebot.check
```

Debe mostrar `OK` en `claude`, `exchange` y `supabase`.

## Ingesta de datos (Fase 1)

```bash
python -m tradebot.ingest                    # retoma desde lo último guardado; si no hay datos, baja 3 años
python -m tradebot.ingest --since 2024-01-01 # vuelve a descargar desde una fecha (upsert, no duplica)
```

Guarda velas cerradas en `candles` y contexto en `market_context`: funding rate (cada 8 h), open interest (cada hora; Binance solo guarda 30 días) y Fear & Greed (diario). Los datos salen del mercado real con un cliente sin llaves, que solo puede leer. Cada fuente corre por separado: si una falla, las demás siguen.

## Backtest (Fase 2)

```bash
python -m tradebot.backtest                    # periodo in-sample, para desarrollar
python -m tradebot.backtest --sin-kill-switch  # diagnóstico: la estrategia en todo el periodo
python -m tradebot.backtest.compare            # compara todas las variantes en 4 sub-periodos
python -m tradebot.backtest --period oos        # evaluación final, una sola vez
```

Simula vela a vela con comisiones, slippage, funding y las reglas de riesgo de `config/settings.toml`, y compara contra comprar y mantener BTC. Ante la duda supone lo peor para el bot (si una vela toca stop y take profit, cuenta el stop).

## Bot en vivo (Fase 4)

1. En Supabase, ejecuta `sql/002_live_trading.sql`.
2. En demo.binance.com, transfiere USDT de Spot a Futuros USDⓈ-M.
3. Corre el bot:

```bash
python -m tradebot.run --once      # un ciclo
python -m tradebot.run             # cada hora, indefinidamente
python -m tradebot.run --reanudar  # quitar kill switch o solo cierre tras revisar
```

Cada ciclo reconcilia la base con el exchange, actualiza el riesgo (pérdida diaria, kill switch), mueve trailing stops y procesa señales nuevas pasando por Claude. Los stops viven en el exchange: protegen aunque el bot esté caído. Si un stop no se puede poner, la posición se cierra de inmediato.

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
src/tradebot/data/          descarga paginada de velas y contexto de mercado
src/tradebot/db.py          lectura y upserts en Supabase
src/tradebot/ingest.py      comando de ingesta
tests/
```
