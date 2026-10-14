"""Tests de humo de la API. Ejecutar: .venv/bin/python -m pytest -q
No dependen de internet: se fuerza el fallback del LLM.
"""
import os

# Vacía (no solo borrada): app/llm.py llama a load_dotenv(), que no pisa variables existentes,
# así una clave en .env no se cuela en los tests.
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app, modelo

NIVELES = {"bueno", "moderado", "alto"}
ENTRADA = {"distrito": modelo.distritos[0], "hora": 9, "dia_semana": 1,
           "trafico": 0.7, "temperatura": 25, "viento": 4}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def predecir(client, **cambios):
    r = client.post("/predict", json={**ENTRADA, **cambios})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_predict_valido(client):
    p = predecir(client)
    assert p["no2_predicho"] > 0
    assert p["nivel"] in NIVELES


def test_mas_trafico_mas_no2(client):
    bajo = predecir(client, trafico=0.1)["no2_predicho"]
    alto = predecir(client, trafico=1.0)["no2_predicho"]
    assert alto > bajo


def test_explicacion_fallback_sin_api_key(client):
    exp = predecir(client)["explicacion"]
    assert exp["fuente"] == "plantilla"
    assert exp["texto"].strip()


def test_hora_invalida_422(client):
    assert client.post("/predict", json={**ENTRADA, "hora": 30}).status_code == 422


def test_distrito_inexistente_404(client):
    assert client.post("/predict", json={**ENTRADA, "distrito": "Atlántida"}).status_code == 404


def test_anomalias_lista(client):
    r = client.get("/anomalies")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
