# Contexto
Prueba técnica de 2 horas (Líderes Digitales, Telefónica). Objetivo: MVP funcional que puntúe en
innovación técnica (20), prueba de concepto (15) y sostenibilidad/inclusión/escalabilidad (15).

# Proyecto
- `data/generate.py` → CSV sintético. `app/model.py` → RandomForest + IsolationForest.
- `app/llm.py` → explicación con LLM, SIEMPRE con fallback (la demo no puede caerse).
- `app/main.py` → FastAPI. `frontend/streamlit_app.py` → UI accesible + pestaña "Sobre el proyecto".
- Arranque: `python data/generate.py`, `uvicorn app.main:app --reload`, `streamlit run frontend/streamlit_app.py`.

# Reglas de trabajo
- Reutiliza esta arquitectura; cambia el dominio, no la estructura. Nada de frontend complejo ni dependencias nuevas sin preguntar.
- Pasos pequeños. Tras cada cambio, ejecútalo/pruébalo tú mismo (curl a la API, import del módulo) antes de decir que funciona.
- Haz `git commit` con un mensaje corto cada vez que algo funcione de punta a punta.
- Mantén las funciones de accesibilidad (lectura fácil, texto grande, contraste, ES/EN, voz, descripciones de gráficos).
- Si algo falla 2 veces, propón una versión más simple.
- Responde en español, directo, sin relleno.
