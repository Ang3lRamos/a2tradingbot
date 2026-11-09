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


# --- contexto v2: lo del v1 más lo que mira un trader antes de tomar una ruptura ---

CHANNEL_BARS = 20  # el canal de donchian-4h-20
DAYS_90 = 90 * BARS_PER_DAY_4H
YEAR = 365 * BARS_PER_DAY_4H


def _channel(candles: pd.DataFrame, direction: int) -> tuple[pd.Series, float]:
    """Canal de las 20 velas anteriores a la señal y el nivel roto (máximo si es long, mínimo si es short)."""
    prior = candles.iloc[-CHANNEL_BARS - 1:-1]
    return prior, float(prior["high"].max() if direction == LONG else prior["low"].min())


def _bars_since_previous_break(candles: pd.DataFrame, direction: int, limit: int = DAYS_90) -> int | None:
    """Velas desde la última ruptura anterior en la misma dirección (sin contar la actual)."""
    close = candles["close"]
    if direction == LONG:
        level = candles["high"].rolling(CHANNEL_BARS).max().shift(1)
        broke = close > level
    else:
        level = candles["low"].rolling(CHANNEL_BARS).min().shift(1)
        broke = close < level
    previous = broke.iloc[-limit - 1:-1]
    # Solo cuenta el inicio de cada ruptura: la vela anterior no rompía.
    starts = previous & ~previous.shift(1, fill_value=False)
    hits = starts[starts].index
    return int(len(candles) - 1 - candles.index.get_loc(hits[-1])) if len(hits) else None


def build_context_v2(asset: AssetFrames, market: AssetFrames, ts: pd.Timestamp, decision_time: pd.Timestamp,
                     direction: int, reason: str, score: float) -> dict:
    context = build_context(asset, market, ts, decision_time, direction, reason, score)
    candles = asset.candles.loc[:ts]
    features = asset.features.loc[:ts]
    close, atr = candles["close"], float(features["atr"].iloc[-1])
    last = float(close.iloc[-1])
    prior, level = _channel(candles, direction)
    tolerance = 0.25 * atr
    touches = int(((prior["high"] >= level - tolerance) if direction == LONG else (prior["low"] <= level + tolerance)).sum())
    window_90 = candles.iloc[-DAYS_90:]
    weekly = close.resample("7D").last().dropna()
    funding = asset.funding[asset.funding.index < decision_time]
    market_candles = market.candles.loc[:ts]
    _, market_level = _channel(market_candles, direction)
    market_last = float(market_candles["close"].iloc[-1])
    market_atr = float(market.features.loc[:ts, "atr"].iloc[-1])

    context["marco_mayor"] = {
        "retorno_90d_pct": _pct_return(close, DAYS_90),
        "tendencia_semanal_cierre_vs_media_10_semanas": _trend_word(weekly.iloc[-1] - weekly.iloc[-10:].mean())
        if len(weekly) >= 10 else None,
        "distancia_al_maximo_90d_en_atr": round((float(window_90["high"].max()) - last) / atr, 2),
        "distancia_al_minimo_90d_en_atr": round((last - float(window_90["low"].min())) / atr, 2),
    }
    context["ruptura"] = {
        "ancho_del_canal_20_velas_en_atr": round((float(prior["high"].max()) - float(prior["low"].min())) / atr, 2),
        "veces_que_se_toco_el_nivel_antes": touches,
        "cierre_mas_alla_del_nivel_en_atr": round((last - level) / atr * (1 if direction == LONG else -1), 2),
        "velas_desde_la_ruptura_anterior_misma_direccion": _bars_since_previous_break(candles, direction),
        "volumen_5_velas_vs_20_velas": round(float(candles["volume"].iloc[-5:].mean() / candles["volume"].iloc[-20:].mean()), 2),
    }
    context["volatilidad_1_ano"] = {
        "percentil_atr_pct_1_ano": _percentile_window(features["atr_pct"], YEAR),
    }
    context["derivados"]["funding_promedio_1d_pct_8h"] = round(float(funding.iloc[-3:].mean()) * 100, 4) if len(funding) else None
    context["derivados"]["funding_promedio_30d_pct_8h"] = round(float(funding.iloc[-90:].mean()) * 100, 4) if len(funding) else None
    context["mercado_general_referente"]["rompe_en_la_misma_direccion"] = bool(
        market_last > market_level if direction == LONG else market_last < market_level)
    context["mercado_general_referente"]["distancia_a_su_nivel_de_ruptura_en_atr"] = round(
        (market_last - market_level) / market_atr * (1 if direction == LONG else -1), 2)
    return context


def _percentile_window(series: pd.Series, window: int) -> float | None:
    values = series.dropna().iloc[-window:]
    if len(values) < 30:
        return None
    return round(float((values < values.iloc[-1]).mean() * 100), 0)
