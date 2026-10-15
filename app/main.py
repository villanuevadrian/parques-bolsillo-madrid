"""API REST. Arranque: uvicorn app.main:app --reload   -> docs en http://localhost:8000/docs"""
from functools import lru_cache
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import explicar
import pandas as pd

from app.model import DATA, Modelo

app = FastAPI(title="Parques bolsillo — API de decisión", version="0.2")
DISTRITOS = sorted(pd.read_csv(DATA / "distritos.csv")["distrito"])


@lru_cache(maxsize=None)
def get_modelo(distrito: str) -> Modelo:
    """Un modelo por distrito, creado la primera vez que se pide (segundos) y reutilizado después."""
    if distrito not in DISTRITOS:
        raise HTTPException(404, f"Distrito desconocido. Opciones: {DISTRITOS}")
    return Modelo(distrito)


modelo = get_modelo("Tetuán")  # precarga el distrito de la demo


class Peticion(BaseModel):
    distrito: str = "Tetuán"
    presupuesto: int = Field(500_000, ge=50_000, le=5_000_000)
    max_plazas: int = Field(10, ge=0, le=200)
    max_mantenimiento: int = Field(20_000, ge=0, le=500_000)
    min_equidad_pct: float = Field(60, ge=0, le=100)
    peso_cobertura: float = Field(1, ge=0, le=5)
    peso_equidad: float = Field(1, ge=0, le=5)
    peso_calor: float = Field(1, ge=0, le=5)
    estilo: Literal["pleno", "facil"] = "pleno"
    idioma: Literal["es", "en"] = "es"


@app.get("/health")
def health():
    return {"ok": True, "mae_temperatura": modelo.mae, "candidatos": len(modelo.cand),
            "barrios": sorted(modelo.celdas["barrio"].unique()), "distritos": DISTRITOS}


@app.get("/ciudad")
def ciudad():
    """Diagnóstico de los 21 distritos con datos abiertos reales del Ayuntamiento."""
    return modelo.distritos.to_dict("records")


@app.get("/barrios")
def barrios(n: int = 131):
    """Detección: los 131 barrios de Madrid ordenados por prioridad (vulnerabilidad + déficit verde), datos reales."""
    return modelo.barrios.head(n).to_dict("records")


@app.get("/diagnostico")
def diagnostico(distrito: str = "Tetuán"):
    modelo = get_modelo(distrito)
    return {"distrito": distrito, "mae_temperatura": modelo.mae,"celdas": modelo.diagnostico(), "barrios": modelo.resumen_barrios(),
            "kpis": modelo.kpis([]), "importancias": modelo.importancias(),
            "anillo": modelo.anillo.to_dict("records"), "parques_existentes": modelo.parques.to_dict("records"),
            "verde_geo": modelo.verde_geo, "barrios_geo": modelo.barrios_geo}


@app.post("/optimizar")
def optimizar(p: Peticion):
    lim = {"presupuesto": p.presupuesto, "max_plazas": p.max_plazas,
           "max_mantenimiento": p.max_mantenimiento, "min_equidad_pct": p.min_equidad_pct}
    pesos = {"cobertura": p.peso_cobertura, "equidad": p.peso_equidad, "calor": p.peso_calor}
    if sum(pesos.values()) == 0:
        raise HTTPException(422, "Al menos una prioridad debe tener peso mayor que 0")
    r = get_modelo(p.distrito).optimizar(lim, pesos)
    r["explicacion"] = explicar(r, "cartera", p.estilo, p.idioma)
    return r


@app.get("/validacion")
def validacion(distrito: str = "Tetuán", presupuesto: int = 500_000):
    """Compara voraz y recocido con el óptimo exacto (programación lineal entera, HiGHS) y con carteras al azar."""
    if not 50_000 <= presupuesto <= 5_000_000:
        raise HTTPException(422, "Presupuesto fuera de rango")
    return get_modelo(distrito).validar(presupuesto)


@app.get("/parque/{pid}")
def parque(pid: int, distrito: str = "Tetuán", estilo: Literal["pleno", "facil"] = "pleno",
           idioma: Literal["es", "en"] = "es"):
    modelo = get_modelo(distrito)
    if pid not in modelo.cand.index:
        raise HTTPException(404, f"Parque candidato {pid} no existe")
    d = modelo.detalle([pid])[0] | {"distrito": distrito}
    d["explicacion"] = explicar(d, "parque", estilo, idioma)
    return d
