"""Gráficos del dashboard.

Paleta categórica de referencia (validada para daltonismo en modo claro y oscuro):
slot 1 azul = el bot, slot 2 naranja = comprar y mantener BTC. El color sigue a la serie,
nunca a su posición. Un solo eje (ambas series en USDT, con el mismo capital inicial).
"""

import altair as alt
import pandas as pd

SERIES = {"equity": "Bot", "btc": "Comprar y mantener BTC"}
PALETTE = {
    "light": {"Bot": "#2a78d6", "Comprar y mantener BTC": "#eb6834", "ink": "#3d3d3a", "grid": "#e8e8e5"},
    "dark": {"Bot": "#3987e5", "Comprar y mantener BTC": "#d95926", "ink": "#c9c9c4", "grid": "#33332f"},
}


MAX_POINTS = 800


def thin(curves: pd.DataFrame, max_points: int = MAX_POINTS) -> pd.DataFrame:
    """Reduce la serie a ~max_points filas (más no se distinguen en pantalla) y conserva siempre la última."""
    if len(curves) <= max_points:
        return curves
    step = -(-len(curves) // max_points)
    return pd.concat([curves.iloc[::step], curves.iloc[[-1]]]).loc[lambda df: ~df.index.duplicated(keep="last")]


def equity_chart(curves: pd.DataFrame, theme: str = "light", height: int = 320) -> alt.LayerChart:
    colors = PALETTE["dark" if theme == "dark" else "light"]
    curves = thin(curves)
    data = (curves.rename(columns=SERIES).rename_axis("fecha").reset_index()
            .melt("fecha", var_name="serie", value_name="capital"))
    names = list(SERIES.values())
    color = alt.Color("serie:N", scale=alt.Scale(domain=names, range=[colors[n] for n in names]),
                      legend=alt.Legend(title=None, orient="top", labelColor=colors["ink"]))
    base = alt.Chart(data).encode(
        x=alt.X("fecha:T", title=None, axis=alt.Axis(grid=False, labelColor=colors["ink"], tickColor=colors["grid"],
                                                    domainColor=colors["grid"], format="%Y-%m", labelOverlap=True)),
        y=alt.Y("capital:Q", title="USDT", scale=alt.Scale(zero=False),
                axis=alt.Axis(gridColor=colors["grid"], labelColor=colors["ink"], titleColor=colors["ink"],
                              domain=False, ticks=False, format=",.0f")),
        color=color,
    )
    lines = base.mark_line(strokeWidth=2, interpolate="monotone")

    # Capa de hover: línea vertical en la fecha más cercana, puntos y tooltip con ambas series.
    nearest = alt.selection_point(nearest=True, on="pointerover", fields=["fecha"], empty=False, clear="pointerout")
    wide = curves.rename(columns=SERIES).rename_axis("fecha").reset_index()
    rule = alt.Chart(wide).mark_rule(color=colors["ink"], opacity=0.4).encode(
        x="fecha:T",
        opacity=alt.condition(nearest, alt.value(0.4), alt.value(0)),
        tooltip=[alt.Tooltip("fecha:T", title="Fecha", format="%d %b %Y %H:%M")]
        + [alt.Tooltip(f"{n}:Q", title=n, format=",.2f") for n in names],
    ).add_params(nearest)
    points = base.mark_point(size=70, filled=True, stroke="white", strokeWidth=2).encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))).transform_filter(nearest)

    # Etiqueta directa al final de cada línea (2 series: leyenda + etiqueta, la identidad no depende solo del color).
    last = data[data["fecha"] == data["fecha"].max()]
    labels = alt.Chart(last).mark_text(align="left", dx=6, fontSize=12, color=colors["ink"]).encode(
        x="fecha:T", y="capital:Q", text=alt.Text("capital:Q", format=",.0f"))

    # Margen derecho para que la etiqueta final no se corte.
    return ((lines + rule + points + labels).properties(height=height, padding={"left": 4, "top": 4, "right": 64, "bottom": 4})
            .configure(background="transparent").configure_view(stroke=None))
