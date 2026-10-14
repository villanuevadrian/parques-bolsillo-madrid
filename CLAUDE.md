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

# Entorno y verificación
- Usa siempre `.venv` (Python 3.12, ya instalado). No reinstales ni recrees el venv.
- Si se aprueba una dependencia nueva: `.venv/bin/pip install X` y añádela a `requirements.txt` en el mismo commit.
- Prueba de punta a punta: `./scripts/smoke.sh`. Al cambiar el dominio, actualiza su `PREDICT_BODY` a los campos nuevos de `/predict`.
- Ver la app: `.claude/launch.json` (API :8000, Streamlit :8501) en el panel del navegador.

# Cierre (antes del último commit) — no olvidar
- Congela versiones: `.venv/bin/pip freeze > requirements.lock.txt` y commitéalo.
- Actualiza README (arranque) y la pestaña "Sobre el proyecto" al dominio final.
- `./scripts/smoke.sh` en verde.
