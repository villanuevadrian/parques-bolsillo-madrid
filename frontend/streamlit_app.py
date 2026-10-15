"""Interfaz. Arranque: streamlit run frontend/streamlit_app.py   (con la API ya levantada)
Accesibilidad: lectura fácil, texto grande, alto contraste, ES/EN, lectura en voz alta,
descripción textual de cada gráfico y mapa. Modo oscuro: menú ⋮ > Settings > Theme.
"""
import json
import os

import httpx
import pandas as pd
import pydeck as pdk
import streamlit as st
import streamlit.components.v1 as components

API = os.getenv("API_URL", "http://localhost:8000")
st.set_page_config(page_title="Parques bolsillo Madrid", page_icon="🌳", layout="wide")

# ---------- Accesibilidad ----------
with st.sidebar:
    st.header("♿ Accesibilidad")
    idioma = st.radio("Idioma / Language", ["es", "en"], horizontal=True)
    facil = st.toggle("Lectura fácil (vecinos y personas mayores)")
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
    "es": {"titulo": "🌳 Parques bolsillo: dónde invertir cada euro para acercar el verde a quien más lo necesita",
           "tab": ["Ciudad (datos reales)", "Diagnóstico del distrito", "Optimizador", "Detalle del parque", "Sobre el proyecto"],
           "boton": "Calcular la mejor cartera de parques", "leer": "🔊 Leer en voz alta"},
    "en": {"titulo": "🌳 Pocket parks: where to invest every euro to bring green space to those who need it most",
           "tab": ["City (real data)", "District diagnosis", "Optimizer", "Park detail", "About"],
           "boton": "Find the best park portfolio", "leer": "🔊 Read aloud"},
}[idioma]
ESTILO = "facil" if facil else "pleno"


def leer_en_voz_alta(texto: str, clave: str):
    """Text-to-speech nativo del navegador (Web Speech API): gratis y sin red."""
    lang = "es-ES" if idioma == "es" else "en-GB"
    components.html(f"""
      <button id="{clave}" style="font-size:1rem;padding:6px 12px;cursor:pointer" aria-label="{T['leer']}"
        onclick='const u=new SpeechSynthesisUtterance({json.dumps(texto)});u.lang="{lang}";
                 speechSynthesis.cancel();speechSynthesis.speak(u);'>{T['leer']}</button>""", height=50)


def api(path, metodo="get", **kw):
    try:
        r = getattr(httpx, metodo)(f"{API}{path}", timeout=60, **kw)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        try:
            detalle = e.response.json().get("detail", e.response.text)
        except ValueError:
            detalle = e.response.text[:200]
        st.warning(f"La API rechazó la petición ({e.response.status_code}): {detalle}")
        st.stop()
    except httpx.HTTPError as e:
        st.error(f"No conecto con la API en {API} ({type(e).__name__}). ¿Está arrancada? (uvicorn app.main:app)")
        st.stop()


def rgba(hex_color: str) -> list[int]:
    h = hex_color.lstrip("#")
    return [int(h[i:i + 2], 16) for i in (0, 2, 4, 6)] if len(h) == 8 else [int(h[i:i + 2], 16) for i in (0, 2, 4)] + [255]


def mapa(celdas: pd.DataFrame, puntos: list[pdk.Layer], diag: dict):
    """Mapa con contornos reales: zonas verdes (OpenStreetMap) y límites oficiales de los barrios."""
    capas = [
        pdk.Layer("GeoJsonLayer", diag["verde_geo"], stroked=True, filled=True, pickable=True,
                  get_fill_color="properties.bolsillo ? [166, 219, 160, 170] : [27, 158, 62, 150]",
                  get_line_color=[27, 120, 55, 255], line_width_min_pixels=1),
        *puntos,
        pdk.Layer("GeoJsonLayer", diag["barrios_geo"], stroked=True, filled=False, pickable=False,
                  get_line_color=[255, 255, 255, 220], line_width_min_pixels=2),
    ]
    span = max(celdas["lat"].max() - celdas["lat"].min(), celdas["lon"].max() - celdas["lon"].min())
    vista = pdk.ViewState(latitude=celdas["lat"].mean(), longitude=celdas["lon"].mean(),
                          zoom=13.6 if span < 0.04 else 12.8 if span < 0.08 else 11.8)
    st.pydeck_chart(pdk.Deck(layers=capas, initial_view_state=vista, map_style=None,
                             tooltip={"text": "{nombre}"}), height=520)


@st.cache_data(ttl=600, show_spinner=False)
def detalle_parque(pid: int, distrito: str, estilo: str, idioma: str) -> dict:
    return api(f"/parque/{pid}", params={"distrito": distrito, "estilo": estilo, "idioma": idioma})


@st.cache_data(ttl=600, show_spinner=False)
def impacto_ejemplo(distrito: str) -> dict:
    return api("/optimizar", "post", json={"distrito": distrito, "presupuesto": 500_000})


def color_deficit(v: float) -> str:
    """Paleta apta para daltonismo: azul (poco déficit) -> naranja (mucho déficit)."""
    v = max(0.0, min(1.0, v))
    r, g, b = (int(a + (bb - a) * v) for a, bb in zip((33, 102, 172), (230, 97, 1)))
    return f"#{r:02x}{g:02x}{b:02x}d0"


st.title(T["titulo"])
health = api("/health")
distrito = st.selectbox("📍 Distrito a analizar (cada uno con su mapa, su padrón y sus parques reales)",
                        health["distritos"], index=health["distritos"].index("Tetuán"))
diag = api("/diagnostico", params={"distrito": distrito})
tabs = st.tabs(T["tab"])

# ---------- 1. Ciudad: datos abiertos reales ----------
with tabs[0]:
    ciudad = pd.DataFrame(api("/ciudad"))
    st.subheader("m² de zonas verdes por habitante en los 21 distritos")
    st.bar_chart(ciudad.set_index("distrito")["m2_hab"], horizontal=True)
    peor = ciudad.loc[ciudad["m2_hab"].idxmin()]
    tetuan = ciudad[ciudad["distrito"] == "Tetuán"].iloc[0]
    st.caption(f"Descripción del gráfico: {peor['distrito']} tiene la menor superficie verde por habitante "
               f"({peor['m2_hab']} m²). Tetuán tiene {tetuan['m2_hab']} m² por habitante.")
    st.info(f"**Por qué Tetuán:** combina poco verde ({tetuan['m2_hab']} m²/hab) con alta vulnerabilidad "
            f"(puesto {int(tetuan['ranking_vulnerabilidad'])} de 21 en el ranking municipal). Los distritos del centro "
            "tienen menos verde, pero son menos vulnerables: los m²/habitante por sí solos no bastan.")
    st.caption("Fuente: datos.madrid.es — Superficie de zonas verdes por distrito (2025), Población por distrito "
               "y barrio (1-ene-2026), Ranking de vulnerabilidad (2020). No incluye parques históricos como el Retiro.")
    with st.expander("Ver tabla de distritos"):
        st.dataframe(ciudad, hide_index=True)

    st.subheader("Detección: barrios con más prioridad de los 131 de Madrid")
    top = pd.DataFrame(api("/barrios", params={"n": 15}))
    st.bar_chart(top.set_index("barrio")["prioridad"], horizontal=True)
    st.caption(f"Descripción del gráfico: {top.iloc[0]['barrio']} ({top.iloc[0]['distrito']}) es el barrio con más "
               "prioridad. Prioridad = 60 % vulnerabilidad del barrio + 40 % déficit de verde del propio barrio "
               "(superficie real de OpenStreetMap). "
               f"El primero de Tetuán es {top[top['distrito'] == 'Tetuán'].iloc[0]['barrio'] if (top['distrito'] == 'Tetuán').any() else '—'}.")
    st.dataframe(top[["puesto", "barrio", "distrito", "poblacion", "ranking_vulnerabilidad", "m2_hab_barrio", "parques_bolsillo",
                      "prioridad"]].rename(columns={"ranking_vulnerabilidad": "puesto vulnerabilidad (de 131)",
                                                    "m2_hab_barrio": "m² verde/hab del barrio",
                                                    "parques_bolsillo": "parques bolsillo existentes"}), hide_index=True)
    st.caption("Escala: distrito para priorizar → barrio para detectar → manzana de 100 m para decidir dónde intervenir "
               "(pestañas siguientes, en el distrito elegido arriba).")

# ---------- 2. Diagnóstico del distrito ----------
with tabs[1]:
    k = diag["kpis"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Mayores y niños con verde a <300 m", f"{k['pct_vulnerables_300m']} %")
    c2.metric("Población con verde a <300 m", f"{k['pct_poblacion_300m']} %")
    c3.metric("m² verde por habitante", k["m2_verde_hab"], help="Referencia habitual (OMS): mínimo 9 m²/hab")
    celdas = pd.DataFrame(diag["celdas"])
    rel = (celdas["indice_deficit"] - celdas["indice_deficit"].min()) / (
        celdas["indice_deficit"].max() - celdas["indice_deficit"].min())  # relativo al distrito
    celdas["color"] = rel.map(color_deficit)
    celdas["size"] = 10 + 45 * rel  # más déficit = punto más grande
    st.subheader("Mapa de déficit verde (cuadrícula de 100 m)")
    anillo = pd.DataFrame(diag["anillo"])
    celdas["rgba"] = celdas["color"].map(rgba)
    celdas["nombre"] = celdas["barrio"] + " · déficit " + celdas["indice_deficit"].astype(str)
    mapa(celdas, [
        pdk.Layer("ScatterplotLayer", anillo, get_position="[lon, lat]", get_radius=12,
                  get_fill_color=[158, 158, 158, 90]),
        pdk.Layer("ScatterplotLayer", celdas, get_position="[lon, lat]", get_radius="size",
                  get_fill_color="rgba", pickable=True),
    ], diag)
    barrios = pd.DataFrame(diag["barrios"])
    st.caption(f"Descripción del mapa: naranja y punto grande = mayor déficit; azul y punto pequeño = menor déficit (lejos de zonas verdes, más calor y más vulnerabilidad). "
               f"Puntos grises: franja de 300 m en distritos vecinos; polígonos verde oscuro: contorno real de los espacios verdes (OpenStreetMap); "
               f"verde claro: parques bolsillo existentes (<0,5 ha); líneas blancas: límites oficiales de los barrios. Cuentan también los de otros distritos, porque para un vecino cuenta la distancia real y no el límite administrativo. "
               f"El barrio con más déficit es {barrios.iloc[0]['barrio']}; el {100 - k['pct_poblacion_300m']:.0f} % de "
               "los vecinos no tiene un espacio verde a menos de 300 m.")
    st.dataframe(barrios.rename(columns={"pct_sin_verde_300m": "% sin verde a 300 m",
                                         "temp_media": "temp. verano (°C)", "deficit_medio": "índice déficit"}),
                 hide_index=True)

# ---------- 3. Optimizador ----------
with tabs[2]:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Presupuesto y restricciones**")
        presupuesto = st.slider("Presupuesto (€)", 100_000, 2_000_000, 500_000, step=50_000)
        max_plazas = st.slider("Máx. plazas de aparcamiento eliminadas", 0, 50, 10)
        max_mant = st.slider("Máx. mantenimiento anual (€)", 5_000, 100_000, 20_000, step=1_000)
        min_eq = st.slider("Mín. % de inversión en barrios vulnerables", 0, 100, 60)
    with c2:
        st.markdown("**Prioridades del técnico**")
        p_cob = st.slider("Cobertura: mayores y niños a <300 m", 0.0, 3.0, 1.0, 0.5)
        p_eq = st.slider("Equidad: barrios más vulnerables", 0.0, 3.0, 1.0, 0.5)
        p_cal = st.slider("Calor: bajar la temperatura en verano", 0.0, 3.0, 1.0, 0.5)

    if st.button(T["boton"], type="primary"):
        with st.spinner("Optimizando (voraz + recocido simulado)…"):
            st.session_state["res"] = api("/optimizar", "post", json={"distrito": distrito,
                "presupuesto": presupuesto, "max_plazas": max_plazas, "max_mantenimiento": max_mant,
                "min_equidad_pct": min_eq, "peso_cobertura": p_cob, "peso_equidad": p_eq, "peso_calor": p_cal,
                "estilo": ESTILO, "idioma": idioma})

    r = st.session_state.get("res")
    r = r if r and r.get("distrito") == distrito else None  # al cambiar de distrito se descarta el resultado
    if r:
        a, d = r["kpis_antes"], r["kpis_despues"]
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Mayores y niños con verde a <300 m", f"{d['pct_vulnerables_300m']} %",
                  f"{d['pct_vulnerables_300m'] - a['pct_vulnerables_300m']:+.1f} pp")
        m2.metric("Parques", d["parques"])
        m3.metric("Inversión", f"{d['inversion']:,} €".replace(",", "."))
        m4.metric("Vecinos con calles más frescas", f"{d['personas_refrescadas']:,}".replace(",", "."))

        st.markdown("**Restricciones** (icono + texto, no solo color)")
        nombres = {"presupuesto": "Presupuesto", "plazas_aparcamiento": "Plazas de aparcamiento",
                   "mantenimiento_anual": "Mantenimiento anual", "equidad_pct_inversion": "% inversión en barrios vulnerables"}
        for n, x in r["restricciones"].items():
            signo = "≥" if n == "equidad_pct_inversion" else "≤"
            st.write(f"{'✅ Cumple' if x['ok'] else '❌ No cumple'} — {nombres[n]}: "
                     f"{x['valor']:,.0f} (límite {signo} {x['limite']:,.0f})".replace(",", "."))

        sel = pd.DataFrame(r["seleccion"])
        st.subheader("Cartera propuesta")
        sel["nombre"] = "Propuesta #" + sel["id"].astype(str) + " · " + sel["tipo"] + " · " + sel["barrio"]
        mapa(celdas, [
            pdk.Layer("ScatterplotLayer", sel, get_position="[lon, lat]", get_radius=300,  # radio OMS de 300 m
                      get_fill_color=[255, 191, 0, 45], get_line_color=[255, 191, 0, 255], stroked=True,
                      line_width_min_pixels=2, pickable=True),
            pdk.Layer("ScatterplotLayer", sel, get_position="[lon, lat]", get_radius=40,
                      get_fill_color=[255, 191, 0, 255], pickable=True),
        ], diag)
        st.caption(f"Descripción del mapa: los {len(sel)} puntos amarillos son los parques bolsillo propuestos y "
                   f"los círculos, su radio de 300 m (sobre el verde real y los límites de barrio); están en {', '.join(sorted(sel['barrio'].unique()))}.")
        st.dataframe(sel[["id", "barrio", "tipo", "m2", "coste", "nuevos_vulnerables_300m", "bajada_temp_c",
                          "coste_por_vecino"]].rename(columns={
                              "nuevos_vulnerables_300m": "mayores y niños nuevos a <300 m",
                              "bajada_temp_c": "°C menos", "coste_por_vecino": "€ por vecino"}), hide_index=True)

        cmp = r["comparativa"]
        if cmp["mejora_pct"] > 0:
            st.caption(f"Algoritmo: el recocido simulado obtiene un {cmp['mejora_pct']} % más de valor que la solución "
                       f"voraz ({cmp['recocido']:,} frente a {cmp['voraz']:,}).".replace(",", "."))
        else:
            st.caption("Algoritmo: el recocido simulado (1.500 iteraciones) no encuentra nada mejor: confirma que la "
                       "solución voraz es la mejor cartera encontrada para estas condiciones.")
        st.info(r["explicacion"]["texto"])
        st.caption(f"Fuente de la explicación: {r['explicacion']['fuente']}")
        leer_en_voz_alta(r["explicacion"]["texto"], "leer_cartera")
    else:
        st.caption("Ajusta presupuesto, restricciones y prioridades y pulsa el botón.")

# ---------- 4. Detalle del parque ----------
with tabs[3]:
    r = st.session_state.get("res")
    r = r if r and r.get("distrito") == distrito else None  # al cambiar de distrito se descarta el resultado
    if not r:
        st.write("Primero calcula una cartera en la pestaña Optimizador.")
    else:
        opciones = {f"#{p['id']} · {p['barrio']} · {p['tipo']}": p["id"] for p in r["seleccion"]}
        pid = opciones[st.selectbox("Parque", list(opciones))]
        p = detalle_parque(pid, distrito, ESTILO, idioma)
        c1, c2, c3 = st.columns(3)
        c1.metric("Vecinos nuevos con verde a <300 m", f"{p['nuevos_vecinos_300m']:,}".replace(",", "."))
        c2.metric("Bajada de temperatura cercana", f"{p['bajada_temp_c']} °C",
                  help=f"Modelo Random Forest, error medio ±{health['mae_temperatura']} °C")
        c3.metric("Coste por vecino", f"{p['coste_por_vecino']} €")
        st.write(f"**{p['tipo']}** · {p['m2']} m² · {p['coste']:,} € · mantenimiento {p['mantenimiento_anual']:,} €/año · "
                 f"agua {p['agua_m3_anual']} m³/año · plazas eliminadas: {p['plazas_perdidas']}".replace(",", "."))
        st.info(p["explicacion"]["texto"])
        st.caption(f"Fuente de la explicación: {p['explicacion']['fuente']}")
        leer_en_voz_alta(p["explicacion"]["texto"], "leer_parque")
        if not facil:
            st.write("**¿Qué influye más en la temperatura?** (explicabilidad del modelo)")
            st.bar_chart(pd.Series(diag["importancias"]))
            st.caption(f"Descripción del gráfico: la variable más influyente es «{next(iter(diag['importancias']))}».")

# ---------- 5. Sobre el proyecto ----------
with tabs[4]:
    ej = impacto_ejemplo(distrito)
    st.success(f"**Impacto en {distrito}:** con 500.000 €, los mayores y niños con un parque a menos de 300 m pasan "
               f"del **{ej['kpis_antes']['pct_vulnerables_300m']} % al {ej['kpis_despues']['pct_vulnerables_300m']} %**, "
               "respetando los límites de aparcamiento, mantenimiento y equidad. Funciona en los 21 distritos.")
    st.markdown(f"""
### Problema
Madrid quiere acercar el verde a sus vecinos, pero el presupuesto es limitado. Los m² de verde por habitante engañan:
el centro tiene menos verde, pero los barrios **vulnerables** sufren más el **calor** y tienen a mayores y niños **lejos** de un parque.

### Usuario
**Técnico municipal** (Junta de Distrito / Medio Ambiente) que debe decidir y **justificar ante el pleno** dónde invertir.
Los vecinos reciben la misma propuesta en **lectura fácil**.

### Solución
Motor de decisión que **detecta** el déficit (proximidad + calor + vulnerabilidad) y **optimiza** dónde construir parques bolsillo:
- **Optimización con restricciones**: cobertura máxima con presupuesto; voraz + **recocido simulado** (metaheurística).
- **ML**: Random Forest como modelo sustituto de la temperatura (error ±{health['mae_temperatura']} °C) → °C que baja cada parque.
- **IA generativa**: informe para el pleno y ficha en lectura fácil, con *fallback*: el servicio nunca se cae.

### Métricas
- **De éxito**: % de mayores y niños con un espacio verde de ≥0,5 ha a <300 m (criterio OMS Europa) o con un parque
  bolsillo nuevo (la micro-intervención para quien no lo tiene), m²/habitante, °C de reducción, coste por vecino.
- **De restricción**: presupuesto, plazas de aparcamiento, mantenimiento anual, % de inversión en barrios vulnerables.

### Datos
**Reales** (datos.madrid.es): zonas verdes por distrito, padrón por barrio 2026, ranking de vulnerabilidad.
**Reales también**: límites oficiales de los 131 barrios, 203 parques municipales con coordenadas y **3.668 zonas
verdes de OpenStreetMap con su contorno** (2.202 de tamaño parque bolsillo, <5.000 m²) → verde real por barrio.
**Sintéticos calibrados**: cuadrícula de 100 m de cada distrito (la población suma el padrón real de cada barrio), temperatura y solares candidatos.
Siguiente paso: inventario de zonas verdes georreferenciado, temperatura satelital (Copernicus) y suelo municipal disponible.

### Inclusión
Prioriza a mayores, niños y barrios vulnerables. Lectura fácil, texto grande, alto contraste, modo oscuro, bilingüe,
voz y descripción textual de mapas y gráficos. Las restricciones se muestran con icono **y** texto.

### Sostenibilidad
Menos islas de calor, especies de bajo consumo de agua (m³/año por parque), coste de mantenimiento como restricción.
Modelos ligeros en CPU. ODS 3, 10, 11 y 13.

### Modelo de negocio y escalabilidad
**SaaS B2G** para ayuntamientos: suscripción anual por municipio. Arquitectura API-first: se replica en cualquier ciudad
cambiando la fuente de datos: Copernicus Urban Atlas (verde), temperatura de superficie Landsat/Sentinel, catastro
y portales de datos abiertos (Barcelona, Valencia…). **IoT** (sensores de temperatura y afluencia) para medir el impacto real tras construir
y reentrenar el modelo: el ciclo de decisión se cierra con datos.

### Metodología y cálculos (cómo se obtiene cada número)
| Cálculo | Fórmula | Justificación / fuente |
|---|---|---|
| **Acceso a verde (KPI principal)** | % de mayores (≥65) y niños (<12) cuya celda está a ≤300 m en línea recta de un espacio verde de ≥0,5 ha | Indicador de la **OMS Europa** (*Urban green spaces: a brief for action*, 2017): verde de 0,5–1 ha a 300 m |
| **Distancia al verde** | distancia en línea recta del centro de la celda al **borde real** más cercano de una zona verde de ≥0,5 ha (borde muestreado cada 20 m; 0 si la celda está dentro) | Contornos de OpenStreetMap. Los 203 parques municipales sin contorno: centro + radio 150 m (parque) / 50 m (jardín) |
| **Verde por habitante** | m² de verde ÷ padrón | Distrito: dato oficial del Ayuntamiento. Barrio: suma de zonas OSM dentro del límite oficial del barrio |
| **Prioridad de barrio** | 0,6 × vulnerabilidad + 0,4 × déficit verde (1 − min(m²/hab, 15)/15) | Vulnerabilidad: ranking oficial del Ayuntamiento. 15 m²/hab: rango alto de las recomendaciones habituales (9–15). Pesos: hipótesis editable |
| **Índice de déficit de celda** | 0,45 × lejanía (dist/600 m) + 0,30 × calor (normalizado) + 0,25 × vulnerabilidad | Pondera la proximidad (criterio OMS) por encima del calor y la equidad. Pesos: hipótesis editable |
| **Bajada de temperatura** | Random Forest (verde, asfalto, densidad → °C) predice antes/después de añadir el parque en las celdas a ≤150 m | Modelo sustituto; error medio ±0,5 °C en validación. Datos de temperatura sintéticos → se recalibra con satélite |
| **Optimización** | max Σ pesos × (vulnerables nuevos a 300 m + equidad + personas refrescadas) sujeto a presupuesto ≤ B; las demás restricciones penalizan un 30 % cada una | Problema de cobertura máxima con presupuesto (NP-difícil): voraz por beneficio/coste + recocido simulado (1.500 iteraciones) |
| **Coste por vecino** | coste del parque ÷ vecinos que ganan verde a 300 m | Costes de urbanización 150–320 €/m² y mantenimiento 3–6 €/m²·año: hipótesis de orden de magnitud |

### Limitaciones (honestidad)
- **Reales**: verde por distrito, padrón y vulnerabilidad por barrio, **límites oficiales de los barrios** y zonas verdes.
- **Verde por barrio**: el Ayuntamiento solo lo publica por distrito; lo calculamos con OpenStreetMap (colaborativo:
  puede faltar o sobrar alguna zona; descartamos jardines sin nombre, que suelen ser patios privados). Validación
  siguiente: Copernicus Urban Atlas o el inventario municipal geocodificado.
- **Parques existentes**: los 203 parques municipales no traen superficie (radio aproximado); las zonas de
  OpenStreetMap sí (radio equivalente a su superficie). Las distancias son en línea recta, no a pie.
- **Sintéticos**: reparto de la población dentro de cada barrio, edades por celda, temperatura y solares candidatos.
  El Random Forest se recalibraría con temperatura satelital real (Landsat/Sentinel) y sensores IoT.
La versión en inglés cubre títulos, pestañas y explicaciones; el resto del contenido está en español.
""")
