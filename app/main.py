"""API REST. Arranque: uvicorn app.main:app --reload   -> docs en http://localhost:8000/docs"""
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import explicar
from app.model import Modelo

app = FastAPI(title="Parques bolsillo — API de decisión", version="0.2")
modelo = Modelo()  # entrena el modelo de temperatura y precalcula coberturas al arrancar (segundos)


class Peticion(BaseModel):
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
            "barrios": sorted(modelo.celdas["barrio"].unique())}


@app.get("/ciudad")
def ciudad():
    """Diagnóstico de los 21 distritos con datos abiertos reales del Ayuntamiento."""
    return modelo.distritos.to_dict("records")


@app.get("/barrios")
def barrios(n: int = 131):
    """Detección: los 131 barrios de Madrid ordenados por prioridad (vulnerabilidad + déficit verde), datos reales."""
    return modelo.barrios.head(n).to_dict("records")


@app.get("/diagnostico")
def diagnostico():
    return {"celdas": modelo.diagnostico(), "barrios": modelo.resumen_barrios(),
            "kpis": modelo.kpis([]), "importancias": modelo.importancias(),
            "anillo": modelo.anillo.to_dict("records"), "parques_existentes": modelo.parques.to_dict("records")}


@app.post("/optimizar")
def optimizar(p: Peticion):
    lim = {"presupuesto": p.presupuesto, "max_plazas": p.max_plazas,
           "max_mantenimiento": p.max_mantenimiento, "min_equidad_pct": p.min_equidad_pct}
    pesos = {"cobertura": p.peso_cobertura, "equidad": p.peso_equidad, "calor": p.peso_calor}
    if sum(pesos.values()) == 0:
        raise HTTPException(422, "Al menos una prioridad debe tener peso mayor que 0")
    r = modelo.optimizar(lim, pesos)
    r["explicacion"] = explicar(r, "cartera", p.estilo, p.idioma)
    return r


@app.get("/parque/{pid}")
def parque(pid: int, estilo: Literal["pleno", "facil"] = "pleno", idioma: Literal["es", "en"] = "es"):
    if pid not in modelo.cand.index:
        raise HTTPException(404, f"Parque candidato {pid} no existe")
    d = modelo.detalle([pid])[0]
    d["explicacion"] = explicar(d, "parque", estilo, idioma)
    return d
