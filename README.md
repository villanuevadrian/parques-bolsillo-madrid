# Aire Madrid — plantilla Smart City (FastAPI + Streamlit + ML + LLM)

Predicción de calidad del aire por distrito y hora, detección de anomalías y explicación en lenguaje natural accesible.

## Arranque (3 terminales o 2 si ya tienes el CSV)
```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python data/generate.py                      # crea data/sample.csv
uvicorn app.main:app --reload                # API -> http://localhost:8000/docs
streamlit run frontend/streamlit_app.py      # (otra terminal) UI -> http://localhost:8501
```
Opcional: copia `.env.example` a `.env` y pon tu `ANTHROPIC_API_KEY`. Sin clave funciona igual (explicaciones por plantilla).

## Arquitectura
`data/` CSV → `app/model.py` (RandomForest + IsolationForest) → `app/main.py` (API REST) → `frontend/` (Streamlit). `app/llm.py` explica la predicción con un LLM y tiene fallback.

## Accesibilidad
Lectura fácil, texto grande, alto contraste, modo oscuro, español/inglés, lectura en voz alta y descripción textual de los gráficos.
