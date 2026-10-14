"""Capa LLM: convierte la predicción en una explicación para el ciudadano.
SIEMPRE tiene fallback: sin API key, sin internet o con error -> texto por plantilla.
La demo nunca se cae por la IA.
"""
import os
from dotenv import load_dotenv

load_dotenv()

ESTILOS = {
    "normal": "Explica en 3 frases claras, con una recomendación práctica.",
    "facil": "Usa lectura fácil: frases muy cortas, palabras sencillas, sin tecnicismos ni cifras complicadas. Pensado para personas mayores.",
}


def _fallback(pred: dict, estilo: str, idioma: str) -> str:
    v, d, n = pred["no2_predicho"], pred["distrito"], pred["nivel"]
    consejo = {
        "bueno": ("Buen momento para pasear o ir en bici.", "Good time for a walk or a bike ride."),
        "moderado": ("Si eres sensible, evita hacer ejercicio intenso en la calle.", "If you are sensitive, avoid intense outdoor exercise."),
        "alto": ("Evita la actividad al aire libre y usa transporte público.", "Avoid outdoor activity and use public transport."),
    }[n][0 if idioma == "es" else 1]
    if idioma == "en":
        return f"Air quality in {d}: {n.upper()} ({v} µg/m³ NO₂). {consejo}"
    if estilo == "facil":
        return f"El aire en {d} está {n.upper()}. {consejo}"
    return f"Se prevén {v} µg/m³ de NO₂ en {d} (nivel {n}). El factor que más influye es el tráfico. {consejo}"


def explicar(pred: dict, estilo: str = "normal", idioma: str = "es") -> dict:
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"texto": _fallback(pred, estilo, idioma), "fuente": "plantilla"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key, timeout=15)
        msg = client.messages.create(
            model=os.getenv("LLM_MODEL", "claude-haiku-4-5"),
            max_tokens=250,
            messages=[{"role": "user", "content": (
                f"Eres un asistente de calidad del aire del Ayuntamiento de Madrid. "
                f"Idioma de respuesta: {'español' if idioma == 'es' else 'inglés'}. {ESTILOS[estilo]}\n"
                f"Datos del modelo: {pred}")}],
        )
        return {"texto": msg.content[0].text, "fuente": "llm"}
    except Exception as e:  # noqa: BLE001  — cualquier fallo -> fallback
        return {"texto": _fallback(pred, estilo, idioma), "fuente": f"plantilla ({type(e).__name__})"}
