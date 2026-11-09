"""Contexto numérico de una señal para el analista IA.

Reglas:
- Solo datos conocidos al cierre de la vela de la señal (momento de decisión).
- Sin fechas, precios absolutos ni nombre de la moneda: Claude conoce la historia del mercado
  hasta su fecha de corte, y con esos datos podría "recordar" qué pasó después.
  Todo va en términos relativos (%, ATRs, percentiles).
"""

from dataclasses import dataclass

import pandas as pd

from tradebot.strategy import LONG

BARS_PER_DAY_4H = 6
PERCENTILE_WINDOW = 90 * BARS_PER_DAY_4H


@dataclass(frozen=True)
class AssetFrames:
    """Series de un activo en la temporalidad de la estrategia, con indicadores ya calculados."""

    candles: pd.DataFrame  # open, high, low, close, volume
    features: pd.DataFrame  # ema_fast, ema_slow, rsi, atr, atr_pct, bb_width
    regime: pd.Series  # +1 / -1 tendencia diaria (día anterior)
    funding: pd.Series  # tasa por cobro, índice horario
    fear_greed: pd.Series  # índice diario


def _pct_return(close: pd.Series, bars: int) -> float | None:
    if len(close) <= bars:
        return None
    return round((close.iloc[-1] / close.iloc[-1 - bars] - 1) * 100, 2)


def _percentile(series: pd.Series) -> float | None:
    window = series.dropna().iloc[-PERCENTILE_WINDOW:]
    if len(window) < 30:
        return None
    return round(float((window < window.iloc[-1]).mean() * 100), 0)


def _trend_word(value: float) -> str | None:
    if pd.isna(value):
        return None
    return "alcista" if value > 0 else "bajista"


def build_context(asset: AssetFrames, market: AssetFrames, ts: pd.Timestamp, decision_time: pd.Timestamp,
                  direction: int, reason: str, score: float) -> dict:
    candles = asset.candles.loc[:ts]
    features = asset.features.loc[:ts]
    close, last = candles["close"], features.iloc[-1]
    funding = asset.funding[asset.funding.index < decision_time]
    fear_greed = asset.fear_greed[asset.fear_greed.index <= decision_time]
    market_close = market.candles.loc[:ts, "close"]

    return {
        "senal": {
            "direccion": "long" if direction == LONG else "short",
            "motivo": reason,
            "fuerza_ruptura_atr": round(float(score), 2),
        },
        "precio": {
            "retorno_4h_pct": _pct_return(close, 1),
            "retorno_24h_pct": _pct_return(close, BARS_PER_DAY_4H),
            "retorno_7d_pct": _pct_return(close, 7 * BARS_PER_DAY_4H),
            "retorno_30d_pct": _pct_return(close, 30 * BARS_PER_DAY_4H),
        },
        "tendencia": {
            "tendencia_4h_ema50_vs_ema200": _trend_word(last["ema_fast"] - last["ema_slow"]),
            "distancia_a_ema200_en_atr": round(float((close.iloc[-1] - last["ema_slow"]) / last["atr"]), 2),
            "tendencia_diaria": _trend_word(asset.regime.loc[:ts].iloc[-1]),
        },
        "momentum_y_volatilidad": {
            "rsi_14": round(float(last["rsi"]), 1),
            "atr_pct_del_precio": round(float(last["atr_pct"]) * 100, 2),
            "percentil_volatilidad_90d": _percentile(features["atr_pct"]),
            "percentil_ancho_bollinger_90d": _percentile(features["bb_width"]),
            "volumen_vs_promedio_20_velas": round(float(candles["volume"].iloc[-1] / candles["volume"].iloc[-21:-1].mean()), 2),
        },
        "derivados": {
            "funding_ultimo_pct_8h": round(float(funding.iloc[-1]) * 100, 4) if len(funding) else None,
            "funding_promedio_7d_pct_8h": round(float(funding.iloc[-21:].mean()) * 100, 4) if len(funding) else None,
        },
        "sentimiento": {
            "fear_greed_0_100": int(fear_greed.iloc[-1]) if len(fear_greed) else None,
        },
        "mercado_general_referente": {
            "retorno_7d_pct": _pct_return(market_close, 7 * BARS_PER_DAY_4H),
            "tendencia_diaria": _trend_word(market.regime.loc[:ts].iloc[-1]),
        },
    }
