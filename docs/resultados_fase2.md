# Resultados de la Fase 2: estrategia base

Fecha de la evaluación out-of-sample: 9 nov 2026. Datos: velas de BTC, ETH y SOL (perpetuos USDT en Binance), con comisión taker de 0,05%, slippage de 0,02% y funding real.

## Método

1. **In-sample** (ene 2024 a nov 2025): se compararon 7 variantes fijadas antes de ver resultados, divididas en 4 sub-periodos. Se eligió la que se mantuvo positiva en todos los sub-periodos y estable ante cambios de su parámetro, no la de mejor retorno.
2. **Out-of-sample** (nov 2025 a nov 2026): una sola corrida con la variante elegida y las reglas de riesgo reales. No se ajustó nada después de verla.

## In-sample

| Variante | Retorno | Máx. DD | Sharpe | Sub-periodos positivos |
|---|---|---|---|---|
| pullback-1h | −33,6% | −43,7% | −1,20 | 2/4 |
| pullback-4h + tendencia | −10,7% | −13,6% | −0,71 | 1/4 |
| donchian-1h-48 | −46,1% | −48,7% | −1,40 | 0/4 |
| **donchian-4h-20** | **+35,0%** | **−11,8%** | **1,05** | **4/4** |
| donchian-4h-55 | +12,8% | −12,1% | 0,59 | 3/4 |
| donchian-4h-20 + tendencia | +10,7% | −12,6% | 0,51 | 3/4 |
| donchian-4h-55 + tendencia | −2,1% | −16,5% | −0,06 | 2/4 |
| Comprar y mantener BTC | +118,4% | −32,4% | 1,12 | 3/4 |

Sin kill switch y con riesgo de 0,5% por operación. Con 0,3% por operación, donchian-4h-20 rinde +21,4% con un drawdown de −7,2%.

## Out-of-sample: donchian-4h-20, riesgo 0,3%

| | donchian-4h-20 | Comprar y mantener BTC |
|---|---|---|
| Retorno neto | −9,8% | −26,4% |
| Máximo drawdown | −10,3% | −45,2% |
| Sharpe | −1,54 | −0,52 |
| Operaciones | 110 | — |
| Tasa de acierto | 28,2% | — |
| Profit factor | 0,58 | — |

El kill switch se activó el 2 abr 2026. Sin él, la estrategia habría terminado el año en −13,9% (profit factor 0,72), con trimestres de −1,2%, −14,5%, +0,3% y +1,5%. Las 6 combinaciones de moneda y dirección perdieron.

## Conclusión

La ventaja que mostró la ruptura de canal en 2024-2025 no se sostuvo en datos nuevos. Perdió menos que comprar y mantener BTC en un año bajista, pero eso viene de operar poco, no de una ventaja propia. El kill switch hizo su trabajo: cortó la pérdida en −10%.

El periodo out-of-sample ya está usado: cualquier ajuste hecho mirándolo sería sobreajuste. La próxima validación limpia es el paper trading en vivo.
