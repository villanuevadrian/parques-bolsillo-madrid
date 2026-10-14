Pega esto como PRIMER mensaje en la IA (Claude, ChatGPT, la que sea), seguido del enunciado del reto.

---

Soy estudiante de 3º de Ingeniería Informática en una prueba técnica de 2 horas: construir una solución tecnológica (aplicación) a un reto. Se permite IA.

**Rúbrica (50 pts):**
- Innovación técnica (20): tecnología de vanguardia, robustez, métodos nuevos, resolución de problemas.
- Prueba de concepto (15): MVP funcional, valida la idea, fácil de llevar a producto.
- Sostenibilidad y escalabilidad (15): prácticas sostenibles e INCLUSIVAS, escala a un mercado mayor, viabilidad a largo plazo.

**Punto de partida:** tengo una plantilla que ya funciona:
- `data/generate.py` → datos sintéticos (CSV)
- `app/model.py` → RandomForest (predicción) + IsolationForest (anomalías), con importancia de variables
- `app/llm.py` → explicación en lenguaje natural con LLM y fallback por plantilla si no hay API
- `app/main.py` → FastAPI (/health, /predict, /anomalies, /stats)
- `frontend/streamlit_app.py` → Streamlit con accesibilidad (lectura fácil, texto grande, alto contraste, ES/EN, voz, descripciones de gráficos) y pestaña "Sobre el proyecto"

**Cómo quiero que trabajes:**
1. Primero propón 2–3 enfoques de MVP realistas para el tiempo y recomienda uno. Reutiliza la plantilla: cambia el dominio, no la arquitectura.
2. Pasos pequeños. Tras cada paso: cómo ejecutarlo y qué debo ver.
3. Archivos COMPLETOS listos para copiar, nunca fragmentos. Indica la ruta de cada archivo.
4. Si te pego un error, ve directo a la solución. Si falla 2 veces, propón algo más simple.
5. Si pido algo demasiado ambicioso para el tiempo que queda, dímelo y recórtalo.
6. Datos sintéticos realistas; nada de frontend complejo.
7. Directo, en español, sin relleno.

Te iré diciendo cuánto tiempo queda. EL RETO ES:
