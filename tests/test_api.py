"""Tests de la API. Ejecutar: .venv/bin/python -m pytest -q
No dependen de internet: se fuerza el fallback del LLM.
"""
import os

# Vacía (no solo borrada): app/llm.py llama a load_dotenv(), que no pisa variables existentes,
# así una clave en .env no se cuela en los tests.
os.environ["ANTHROPIC_API_KEY"] = ""

import pytest
from fastapi.testclient import TestClient

from app.main import app, modelo

BASE = {"presupuesto": 500_000, "max_plazas": 10, "max_mantenimiento": 20_000, "min_equidad_pct": 60}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def resultado(client):
    r = client.post("/optimizar", json=BASE)
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_ciudad_datos_reales(client):
    d = client.get("/ciudad").json()
    assert len(d) == 21  # los 21 distritos de Madrid
    tetuan = next(x for x in d if x["distrito"] == "Tetuán")
    assert 0 < tetuan["m2_hab"] < 10


def test_detecta_131_barrios(client):
    b = client.get("/barrios").json()
    assert len(b) == 131
    assert b[0]["prioridad"] >= b[-1]["prioridad"]  # ordenados de mayor a menor prioridad


def test_poblacion_calibrada_con_padron():
    assert abs(modelo.celdas["poblacion"].sum() - 167_776) < 50  # Tetuán, padrón 1-ene-2026


def test_optimizar_respeta_presupuesto(resultado):
    assert resultado["kpis_despues"]["inversion"] <= BASE["presupuesto"]
    assert resultado["restricciones"]["presupuesto"]["ok"]
    assert len(resultado["seleccion"]) >= 1


def test_optimizar_mejora_kpis(resultado):
    assert resultado["kpis_despues"]["pct_vulnerables_300m"] > resultado["kpis_antes"]["pct_vulnerables_300m"]


def test_recocido_no_empeora_al_voraz(resultado):
    assert resultado["comparativa"]["recocido"] >= resultado["comparativa"]["voraz"]


def test_mas_presupuesto_no_empeora(client, resultado):
    r = client.post("/optimizar", json={**BASE, "presupuesto": 1_000_000}).json()
    assert r["kpis_despues"]["pct_vulnerables_300m"] >= resultado["kpis_despues"]["pct_vulnerables_300m"]


def test_parques_enfrian(resultado):
    assert all(p["bajada_temp_c"] >= 0 for p in resultado["seleccion"])


def test_explicacion_fallback_sin_api_key(resultado):
    exp = resultado["explicacion"]
    assert exp["fuente"] == "plantilla" and exp["texto"].strip()


def test_parque_detalle_y_lectura_facil(client, resultado):
    pid = resultado["seleccion"][0]["id"]
    r = client.get(f"/parque/{pid}", params={"estilo": "facil"})
    assert r.status_code == 200 and r.json()["explicacion"]["texto"].strip()


def test_entradas_invalidas(client):
    assert client.post("/optimizar", json={**BASE, "presupuesto": 10}).status_code == 422
    assert client.post("/optimizar", json={**BASE, "peso_cobertura": 0, "peso_equidad": 0,
                                           "peso_calor": 0}).status_code == 422
    assert client.get("/parque/9999").status_code == 404


def test_explicacion_en_ingles(client):
    r = client.post("/optimizar", json={**BASE, "idioma": "en"}).json()
    assert "pocket parks" in r["explicacion"]["texto"]


def test_limites_reales_y_anillo_300m(client):
    d = client.get("/diagnostico").json()
    assert len(d["anillo"]) > 0  # franja de 300 m en distritos vecinos
    assert any("Tetuán" not in p["nombre"] for p in d["parques_existentes"])  # cuenta verde de otros distritos
    assert set(modelo.celdas["barrio"]) == {"Almenara", "Bellas Vistas", "Berruguete", "Castillejos",
                                             "Cuatro Caminos", "Valdeacederas"}
