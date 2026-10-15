"""Capa LLM: convierte la propuesta del optimizador en texto para cada público.
- "pleno": informe justificativo para el técnico municipal (lo presenta en la Junta de Distrito).
- "facil": ficha en lectura fácil para vecinos y personas mayores.
SIEMPRE tiene fallback: sin API key, sin internet o con error -> texto por plantilla.
La demo nunca se cae por la IA.
"""
import os
from dotenv import load_dotenv

load_dotenv()

ESTILOS = {
    "pleno": "Redacta un informe técnico breve (máx. 120 palabras) para justificar la inversión ante el pleno "
             "de la Junta de Distrito: impacto, equidad, restricciones cumplidas y una recomendación.",
    "facil": "Usa lectura fácil: frases muy cortas, palabras sencillas, sin tecnicismos ni cifras complicadas. "
             "Pensado para vecinos y personas mayores. Máx. 60 palabras. Redondea las cifras (p. ej. 'unas 16.000 '"
             "personas'). No hagas preguntas al lector.",
}


def _n(x) -> str:
    """Miles con punto (formato español): 12500 -> 12.500."""
    return f"{x:,.0f}".replace(",", ".")


def _fallback_cartera(r: dict, estilo: str, idioma: str) -> str:
    a, d, n = r["kpis_antes"], r["kpis_despues"], r["kpis_despues"]["parques"]
    if idioma == "en":
        return (f"{n} pocket parks for €{d['inversion']:,}. Vulnerable residents (65+ and under 12) with green space "
                f"within 300 m rise from {a['pct_vulnerables_300m']}% to {d['pct_vulnerables_300m']}%. "
                f"{d['personas_refrescadas']:,} people get cooler streets in heat waves.")
    if estilo == "facil":
        return (f"Vamos a crear {n} parques pequeños en {r.get('distrito', 'tu distrito')}. Más mayores y niños tendrán un parque cerca de casa. "
                f"En verano, sus calles estarán más frescas.")
    ok = sum(x["ok"] for x in r["restricciones"].values())
    return (f"Se proponen {n} parques bolsillo con una inversión de {_n(d['inversion'])} €. La población vulnerable "
            f"(mayores de 65 y menores de 12) con zona verde a menos de 300 m pasa del {a['pct_vulnerables_300m']}% "
            f"al {d['pct_vulnerables_300m']}%, y {_n(d['personas_refrescadas'])} vecinos se benefician de calles más "
            f"frescas en olas de calor. Se cumplen {ok} de {len(r['restricciones'])} restricciones. "
            f"Recomendación: aprobar la cartera y medir el efecto con sensores IoT de temperatura.")


def _fallback_parque(p: dict, estilo: str, idioma: str) -> str:
    if idioma == "en":
        return (f"New pocket park in {p['barrio']} ({p['m2']} m²). {p['nuevos_vecinos_300m']:,} people will have "
                f"green space within 300 m. Streets around it will be about {p['bajada_temp_c']} °C cooler in summer.")
    if estilo == "facil":
        return (f"Habrá un parque nuevo en {p['barrio']}. Estará cerca de tu casa. Tendrá "
                f"{', '.join(e['elemento'].split(' (')[0].lower() for e in p.get('diseno', {}).get('elementos', [])[:3]) or 'sombra y bancos'}. "
                f"En verano, la calle estará más fresca.")
    return (f"Parque bolsillo en {p['barrio']} ({p['tipo'].lower()}, {p['m2']} m², {_n(p['coste'])} €). "
            f"{_n(p['nuevos_vecinos_300m'])} vecinos ganan zona verde a menos de 300 m, de ellos "
            f"{_n(p['nuevos_vulnerables_300m'])} mayores o niños. Bajada estimada de {p['bajada_temp_c']} °C en las "
            f"calles cercanas. Coste por vecino beneficiado: {p['coste_por_vecino']} €. Incluye: "
            f"{', '.join(e['elemento'].lower() for e in p.get('diseno', {}).get('elementos', [])) or 'diseño pendiente'}.")


def explicar(datos: dict, tipo: str = "cartera", estilo: str = "pleno", idioma: str = "es") -> dict:
    """tipo: 'cartera' (resultado del optimizador) o 'parque' (un parque concreto)."""
    fallback = _fallback_cartera if tipo == "cartera" else _fallback_parque
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return {"texto": fallback(datos, estilo, idioma), "fuente": "plantilla"}
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key, timeout=15)
        msg = client.messages.create(
            model=os.getenv("LLM_MODEL", "claude-haiku-4-5"),
            max_tokens=350,
            messages=[{"role": "user", "content": (
                "Eres el asistente de planificación de zonas verdes del Ayuntamiento de Madrid (el distrito viene en los datos). "
                f"Idioma de respuesta: {'español' if idioma == 'es' else 'inglés'}. {ESTILOS[estilo]} "
                "Usa solo los datos facilitados, no inventes cifras. 'comparativa.mejora_pct' es la mejora del "
                "recocido simulado frente al algoritmo voraz; 'pct_vulnerables_300m' es el % de mayores y niños con "
                "verde (criterio OMS) o parque bolsillo nuevo a menos de 300 m; 'personas_refrescadas' son vecinos con calles "
                "más frescas (no con verde cerca); 'plazas_aparcamiento.valor' son plazas que SÍ se eliminan. "
                "Sé exacto con estos significados.\n"
                f"Datos: {datos}")}],
        )
        return {"texto": msg.content[0].text, "fuente": "llm"}
    except Exception as e:  # noqa: BLE001  — cualquier fallo -> fallback
        return {"texto": fallback(datos, estilo, idioma), "fuente": f"plantilla ({type(e).__name__})"}
