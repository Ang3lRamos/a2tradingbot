"""Prompt del analista IA. Cambiar el texto cambia lo que se mide: subir PROMPT_VERSION."""

import json

PROMPT_VERSION = "v1"  # el que usa el bot en vivo

TEMPLATE = """Eres el analista de riesgo de un bot que opera futuros perpetuos de criptomonedas en papel.
Una estrategia de ruptura de canal en velas de 4 horas generó la señal de abajo. La operación
usaría un stop inicial de 1,5 ATR con trailing stop, y arriesga una fracción fija del capital.

Tu trabajo es decidir si se ejecuta:
- "approve": se opera con el tamaño completo.
- "reduce": se opera con un tamaño menor (size_multiplier entre 0.1 y 0.9).
- "veto": no se opera.
No puedes cambiar la dirección ni el stop, ni aumentar el tamaño.

Evalúa si el contexto favorece o perjudica la operación: alineación de la tendencia, momentum
agotado, volatilidad, posicionamiento en derivados (funding), sentimiento y mercado general.
Los datos no incluyen fechas, precios absolutos ni el nombre del activo, a propósito: no intentes
adivinar el periodo ni el activo; decide solo con estos números.

Contexto (JSON):
{context}

Responde SOLO con un objeto JSON, sin texto antes ni después, con este formato:
{{"decision": "approve" | "reduce" | "veto", "confidence": 0.0 a 1.0, "size_multiplier": 0.0 a 1.0,
 "reasons": ["razón breve", "..."], "risk_flags": ["riesgo", "..."]}}
Con "approve" usa size_multiplier 1.0; con "veto", 0.0."""


TEMPLATE_V2 = """Eres un trader profesional de futuros de criptomonedas que filtra señales de un sistema
de seguimiento de tendencia. El sistema compra cuando una vela de 4 horas cierra sobre el máximo de
las 20 velas anteriores (vende en corto cuando cierra bajo el mínimo). Entra al cierre, con un stop
inicial de 1,5 ATR que luego sigue al precio (trailing), sin objetivo de ganancia fijo.

Cómo gana este sistema: la mayoría de las operaciones pierden poco (alrededor de -1R) y unas pocas
ganan mucho cuando la ruptura inicia una tendencia sostenida. Tu tarea es estimar si ESTA ruptura
tiene más o menos probabilidad que una ruptura típica de convertirse en una tendencia que pague.

Analiza como lo haría un trader:
1. Contexto de tendencia en marcos mayores (diario, semanal, 90 días): ¿la ruptura va a favor o en contra?
2. Calidad de la ruptura: rango previo (ancho del canal, cuántas veces se probó el nivel), fuerza del
   cierre, volumen en la ruptura y su evolución reciente. Rangos largos y comprimidos que se rompen
   con volumen suelen ser mejores; rupturas tardías y extendidas, peores.
3. Agotamiento: distancia a extremos de 90 días, RSI, distancia a la EMA200 en ATR.
4. Régimen de volatilidad: percentiles de ATR y Bollinger (compresión antes de expansión es favorable).
5. Posicionamiento: funding reciente frente al de 30 días (funding muy alto a favor de la dirección
   = posiciones saturadas).
6. Mercado general: ¿el activo de referencia acompaña en la misma dirección?

Los datos no incluyen fechas, precios absolutos ni el nombre del activo, a propósito: no intentes
adivinar el periodo ni el activo; decide solo con estos números.

Contexto (JSON):
{context}

Responde SOLO con un objeto JSON, sin texto antes ni después:
{{"score": entero de 0 a 100, "reasons": ["razón breve", "..."], "risk_flags": ["riesgo", "..."]}}
"score" es tu estimación de la calidad de esta operación frente a una ruptura típica del mismo
sistema: 50 = típica, más de 50 = mejor que el promedio, menos de 50 = peor. Usa toda la escala:
si todas las señales reciben un puntaje parecido, el puntaje no sirve para distinguirlas."""

PROMPTS = {"v1": TEMPLATE, "v2": TEMPLATE_V2}


def render_prompt(context: dict, active_rules: list[str] | None = None, version: str = PROMPT_VERSION) -> str:
    prompt = PROMPTS[version].format(context=json.dumps(context, ensure_ascii=False, indent=1))
    if active_rules:
        rules = "\n".join(f"- {rule}" for rule in active_rules)
        prompt += f"\n\nReglas aprendidas y validadas que debes tener en cuenta:\n{rules}"
    return prompt
