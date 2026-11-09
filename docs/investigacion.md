# Registro de investigación

Cada idea se anota **antes** de probarla, con cuántas variantes se intentan. Así se sabe cuántos intentos hubo detrás de un buen resultado: si se prueban muchas, la mejor sale bien por suerte.

Intentos acumulados: **7 variantes de estrategia** (lista fija en `backtest/variants.py`) y **1 prompt de IA** (v1).

---

## 2026-11-09 · Bug en el R múltiplo

Con trailing stop, el R de cada operación se dividía por la distancia al stop ya movido, no por el riesgo inicial. Las ganancias quedaban topadas en ~1R y aparecían pérdidas de −31R. El P&L y el capital estaban bien; el R promedio y la evaluación de la IA no.

| | Antes | Corregido |
|---|---|---|
| R medio in-sample (donchian-4h-20) | −0,26 | +0,15 |
| Habilidad de la IA (300 señales) | +0,003 | +0,043 (IC 90%: −0,009 a +0,094) |

## 2026-11-09 · Historia desde 2019 y prueba hacia atrás

Se descargaron velas de 1h desde 2019-09 (BTC), 2019-11 (ETH) y 2020-09 (SOL). El in-sample y la muestra de la IA quedaron fijos en sus fechas originales (`is_start`, `SAMPLE_START`), y se verificó que no cambiaron.

El tramo 2020-11 a 2024-01 nunca se usó para elegir la estrategia. donchian-4h-20 sin kill switch: **+8,2%**, Sharpe 0,31, caída máxima −15,5%. Con el kill switch del 10% se detiene en marzo de 2021.

## 2026-11-09 · Walk-forward 2022–2026

`python -m tradebot.backtest.walkforward`. Cada enero se elige, entre las 7 variantes, la de mejor Sharpe en todo lo anterior y se opera ese año. Sin kill switch, riesgo de 0,3% por operación.

Retorno por año de cada variante:

| variante | 2021 | 2022 | 2023 | 2024 | 2025 | 2026* |
|---|---|---|---|---|---|---|
| pullback-1h | −10,6% | −10,8% | +0,0% | −14,4% | −19,4% | −1,9% |
| pullback-4h+tend | +4,1% | +2,5% | +2,2% | −5,6% | +2,3% | +1,5% |
| donchian-1h-48 | −20,2% | −5,9% | +0,9% | −16,9% | −24,1% | −15,8% |
| donchian-4h-20 | −9,0% | +4,9% | +11,2% | +9,8% | +1,7% | −7,7% |
| donchian-4h-55 | −7,6% | +1,2% | +9,8% | +1,2% | +3,9% | −1,4% |
| donchian-4h-20+tend | −2,7% | +2,4% | +13,8% | −0,1% | +2,4% | −4,4% |
| donchian-4h-55+tend | −7,3% | +0,1% | +11,7% | −2,4% | −0,9% | −1,7% |
| BTC comprar y mantener | +57,4% | −65,4% | +154,6% | +111,4% | −7,4% | −15,0% |

\* 2026 hasta el 9 de noviembre.

Resultado encadenado 2022–2026:

| | Retorno | Anual | Caída máx. | Sharpe |
|---|---|---|---|---|
| Bot (walk-forward) | +2,6% | +0,5% | −14,0% | 0,11 |
| Bot a igual riesgo que BTC (x6,6) | −27,2% | −6,3% | −67,4% | 0,11 |
| BTC comprar y mantener | +46,6% | +8,2% | −66,9% | 0,41 |

**Conclusiones**

1. Ninguna variante le gana a BTC ajustando por riesgo. El walk-forward deja un Sharpe de 0,11 contra 0,41 de BTC.
2. Las variantes en 1h pierden todos los años: las comisiones y el ruido se comen las rupturas cortas.
3. Elegir por Sharpe pasado no acierta: la variante "ganadora" cambia y la elegida rinde menos que donchian-4h-20 fija. Las diferencias entre variantes de 4h son mayormente ruido.
4. Las rupturas en 4h tienen una ventaja chica y positiva en la mayoría de los años, pero no alcanza para cubrir el costo de estar casi siempre fuera del mercado frente a BTC.

**Próximas ideas** (anotar aquí antes de probarlas):

- Seguimiento de tendencia con tamaño por volatilidad, siempre en el mercado (no solo en rupturas).
- Momentum relativo entre más monedas.
- Estrategias de funding o basis.
- Prompt v2 de la IA con más contexto y puntaje de 0 a 100, sobre 300 señales nuevas.
