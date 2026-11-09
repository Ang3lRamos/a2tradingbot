"""Prompt del analista IA. Cambiar el texto cambia lo que se mide: subir PROMPT_VERSION."""

import json

PROMPT_VERSION = "v1"

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


def render_prompt(context: dict, active_rules: list[str] | None = None) -> str:
    prompt = TEMPLATE.format(context=json.dumps(context, ensure_ascii=False, indent=1))
    if active_rules:
        rules = "\n".join(f"- {rule}" for rule in active_rules)
        prompt += f"\n\nReglas aprendidas y validadas que debes tener en cuenta:\n{rules}"
    return prompt
