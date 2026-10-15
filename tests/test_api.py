"""Tests de la API. Ejecutar: .venv/bin/python -m pytest -q
No dependen de internet: se fuerza el fallback del LLM.
"""
import os

# Vacía (no solo borrada): app/llm.py llama a load_dotenv(), que no pisa variables existentes,
# así una clave en .env no se cuela en los tests.
os.environ["ANTHROPIC_API_KEY"] = ""

import numpy as np
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
    assert any(p["bolsillo"] for p in d["parques_existentes"])  # parques bolsillo reales de OpenStreetMap
    assert set(modelo.celdas["barrio"]) == {"Almenara", "Bellas Vistas", "Berruguete", "Castillejos",
                                             "Cuatro Caminos", "Valdeacederas"}


def test_otro_distrito_funciona(client):
    r = client.post("/optimizar", json={**BASE, "distrito": "Puente de Vallecas"}).json()
    assert r["distrito"] == "Puente de Vallecas"
    assert r["kpis_despues"]["pct_vulnerables_300m"] > r["kpis_antes"]["pct_vulnerables_300m"]
    assert client.get("/diagnostico", params={"distrito": "Atlántida"}).status_code == 404


@pytest.mark.parametrize("distrito", ["Usera", "Fuencarral-El Pardo", "Centro"])
def test_diagnostico_todos_los_tipos_de_distrito(client, distrito):
    assert client.get("/diagnostico", params={"distrito": distrito}).status_code == 200


def test_verde_por_barrio_osm(client):
    b = client.get("/barrios").json()
    assert all("m2_hab_barrio" in x and "parques_bolsillo" in x for x in b)
    assert sum(x["parques_bolsillo"] for x in b) > 1000  # Madrid tiene miles de zonas verdes pequeñas


# ---------- Auditoría de cálculos (recalculados de forma independiente) ----------
def _dentro(lon, lat, poly):
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cr = ((y[None] > lat[:, None]) != (y2[None] > lat[:, None])) & (
        lon[:, None] < (x2 - x)[None] * (lat[:, None] - y[None]) / ((y2 - y)[None] + 1e-15) + x[None])
    return cr.sum(axis=1) % 2 == 1


def test_auditoria_celdas_dentro_de_su_barrio_oficial():
    c = modelo.celdas
    dentro = 0
    for f in modelo.barrios_geo["features"]:
        sub = c[c["barrio"] == f["properties"]["nombre"]]
        dentro += _dentro(sub["lon"].to_numpy(), sub["lat"].to_numpy(), np.array(f["geometry"]["coordinates"][0])).sum()
    assert dentro == len(c)


def test_auditoria_poblacion_igual_al_padron_por_barrio():
    padron = modelo.barrios.set_index("barrio")["poblacion"]
    suma = modelo.celdas.groupby("barrio")["poblacion"].sum()
    assert (suma - padron.reindex(suma.index)).abs().max() <= 50  # solo redondeo


def test_auditoria_cobertura_recalculada_a_mano(resultado):
    c, M_LON, M_LAT = modelo.celdas, 84_500, 111_000
    cub = c["dist_verde_m"].to_numpy() <= 300
    for p in resultado["seleccion"]:
        cub |= (np.hypot((c["lon"] - p["lon"]) * M_LON, (c["lat"] - p["lat"]) * M_LAT) <= 300.5).to_numpy()
    pct = 100 * c["vulnerables"][cub].sum() / c["vulnerables"].sum()
    assert abs(pct - resultado["kpis_despues"]["pct_vulnerables_300m"]) < 0.2
    assert sum(p["coste"] for p in resultado["seleccion"]) == resultado["kpis_despues"]["inversion"]



@pytest.mark.parametrize("distrito,presupuesto", [("Tetuán", 500_000), ("Puente de Vallecas", 250_000)])
def test_validacion_contra_optimo_exacto(client, distrito, presupuesto):
    v = client.get("/validacion", params={"distrito": distrito, "presupuesto": presupuesto}).json()
    assert "Optimal" in v["estado_solver"]
    assert v["recocido"] <= v["optimo_exacto"] + 1          # ninguna heurística supera al óptimo exacto
    assert v["recocido_pct_optimo"] >= 95                    # el recocido queda a <5 % del óptimo
    assert v["recocido"] >= v["voraz"]
    assert v["veces_mejor_que_azar"] > 1.5



def test_diseno_respeta_superficie_y_presupuesto(resultado):
    for p in resultado["seleccion"]:
        d = p["diseno"]
        assert d["elementos"], "cada parque debe tener al menos un elemento"
        assert d["m2_usados"] <= d["m2_disponibles"]
        assert d["coste_equipamiento"] <= d["presupuesto_equipamiento"]
