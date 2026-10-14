"""Interfaz. Arranque: streamlit run frontend/streamlit_app.py   (con la API ya levantada)
Accesibilidad: lectura fácil, texto grande, alto contraste, ES/EN, lectura en voz alta,
descripción textual de cada gráfico. Modo oscuro: menú ⋮ > Settings > Theme.
"""
import json
import os

import httpx
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Aire Madrid", page_icon="🌿", layout="wide")

# ---------- Accesibilidad ----------
with st.sidebar:
    st.header("♿ Accesibilidad")
    idioma = st.radio("Idioma / Language", ["es", "en"], horizontal=True)
    facil = st.toggle("Lectura fácil (personas mayores)")
    grande = st.toggle("Texto grande")
    contraste = st.toggle("Alto contraste")
    st.caption("Modo oscuro: menú ⋮ arriba a la derecha → Settings → Theme.")

css = ""
if grande:
    css += "html, body, [class*='css'], p, label, li {font-size: 1.3rem !important;}"
if contraste:
    css += ".stApp {background:#000 !important; color:#fff !important;} p,label,h1,h2,h3,li,span {color:#fff !important;}"
if css:
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)

T = {  # textos ES/EN
    "es": {"titulo": "🌿 Aire Madrid: predicción y alertas de calidad del aire",
           "tab": ["Predicción", "Panel ciudad", "Anomalías", "Sobre el proyecto"], "boton": "Predecir",
           "leer": "🔊 Leer en voz alta"},
    "en": {"titulo": "🌿 Madrid Air: air quality forecasting and alerts",
           "tab": ["Forecast", "City dashboard", "Anomalies", "About"], "boton": "Forecast",
           "leer": "🔊 Read aloud"},
}[idioma]


def leer_en_voz_alta(texto: str):
    """Text-to-speech nativo del navegador (Web Speech API): gratis y sin red."""
    lang = "es-ES" if idioma == "es" else "en-GB"
    components.html(f"""
      <button style="font-size:1rem;padding:6px 12px;cursor:pointer" aria-label="{T['leer']}"
        onclick='const u=new SpeechSynthesisUtterance({json.dumps(texto)});u.lang="{lang}";
                 speechSynthesis.cancel();speechSynthesis.speak(u);'>{T['leer']}</button>""", height=50)


def api_get(path):
    try:
        return httpx.get(f"{API}{path}", timeout=10).json()
    except httpx.HTTPError:
        st.error(f"No conecto con la API en {API}. ¿Está arrancada? (uvicorn app.main:app)")
        st.stop()


st.title(T["titulo"])
health = api_get("/health")
tab1, tab2, tab3, tab4 = st.tabs(T["tab"])

# ---------- 1. Predicción ----------
with tab1:
    c1, c2 = st.columns(2)
    with c1:
        distrito = st.selectbox("Distrito", health["distritos"])
        hora = st.slider("Hora", 0, 23, 9)
        dia = st.selectbox("Día", range(7), format_func=lambda i: ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][i])
    with c2:
        trafico = st.slider("Intensidad de tráfico (0-1)", 0.0, 1.2, 0.7)
        temp = st.slider("Temperatura (°C)", -5.0, 45.0, 25.0)
        viento = st.slider("Viento (km/h)", 0.0, 30.0, 4.0)

    if st.button(T["boton"], type="primary"):
        r = httpx.post(f"{API}/predict", timeout=30, json={
            "distrito": distrito, "hora": hora, "dia_semana": dia, "trafico": trafico,
            "temperatura": temp, "viento": viento, "estilo": "facil" if facil else "normal", "idioma": idioma,
        }).json()
        color = {"bueno": "🟢", "moderado": "🟡", "alto": "🔴"}[r["nivel"]]
        st.metric("NO₂ (µg/m³)", r["no2_predicho"], help=f"Error medio del modelo: ±{r['error_medio_modelo']}")
        st.subheader(f"{color} {r['nivel'].upper()}")  # icono + texto: no depende solo del color
        st.info(r["explicacion"]["texto"])
        st.caption(f"Fuente de la explicación: {r['explicacion']['fuente']}")
        leer_en_voz_alta(r["explicacion"]["texto"])
        if not facil:
            st.write("**¿Qué influye más en la predicción?** (explicabilidad)")
            st.bar_chart(pd.Series(r["factores"]))
            top = next(iter(r["factores"]))
            st.caption(f"Descripción del gráfico: la variable más influyente es «{top}».")

# ---------- 2. Panel ----------
with tab2:
    s = api_get("/stats")
    dfd = pd.DataFrame(s["distritos"]).set_index("distrito")
    st.subheader("NO₂ medio por distrito")
    st.bar_chart(dfd["no2_medio"])
    peor = dfd["no2_medio"].idxmax()
    st.caption(f"Descripción del gráfico: {peor} es el distrito con peor calidad media ({dfd.loc[peor, 'no2_medio']} µg/m³).")
    st.subheader("Perfil horario")
    st.line_chart(pd.DataFrame(s["perfil_horario"]).set_index("hora"))
    st.caption("Descripción del gráfico: picos en horas punta de mañana y tarde, coincidiendo con el tráfico.")

# ---------- 3. Anomalías ----------
with tab3:
    st.write("Lecturas atípicas detectadas automáticamente (IsolationForest): posibles obras, incidentes o sensores averiados.")
    st.dataframe(pd.DataFrame(api_get("/anomalies")), use_container_width=True)

# ---------- 4. Sobre el proyecto (se vende sola) ----------
with tab4:
    st.markdown(f"""
### Problema
La contaminación por NO₂ en Madrid se concentra en horas y zonas concretas, pero el ciudadano no sabe **cuándo** ni **dónde** evitarla.

### Solución
Plataforma que **predice** la calidad del aire por distrito y hora, **detecta anomalías** y lo **explica en lenguaje natural** adaptado a cada persona.

### Tecnología
- **ML ligero y explicable**: Random Forest (error medio ±{health['mae']} µg/m³) + Isolation Forest para anomalías. Entrena en segundos en CPU.
- **IA generativa** para explicar resultados, con *fallback* determinista: el servicio nunca se cae.
- **Arquitectura API-first** (FastAPI): la misma API sirve web, app móvil, paneles municipales o chatbots.

### Inclusión
Lectura fácil para personas mayores, texto grande, alto contraste, modo oscuro, bilingüe, lectura en voz alta y descripción textual de los gráficos. Los niveles se indican con icono **y** texto, no solo con color.

### Sostenibilidad
Modelos de bajo consumo (sin GPU). Objetivo: reducir exposición a contaminación y fomentar movilidad sostenible (ODS 3, 11 y 13).

### Escalabilidad
Hoy: datos sintéticos. Mañana: conectado al portal de **datos abiertos del Ayuntamiento** (estaciones de calidad del aire, aforos de tráfico, AEMET). Se replica en cualquier ciudad cambiando la fuente de datos. Contenedorizable con Docker.
""")
