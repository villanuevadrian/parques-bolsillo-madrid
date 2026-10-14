"""API REST. Arranque: uvicorn app.main:app --reload   -> docs en http://localhost:8000/docs"""
from typing import Literal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.llm import explicar
from app.model import Modelo

app = FastAPI(title="Smart City API", version="0.1")
modelo = Modelo()  # se entrena al arrancar (segundos)


class Entrada(BaseModel):
    distrito: str
    hora: int = Field(ge=0, le=23)
    dia_semana: int = Field(ge=0, le=6)
    trafico: float = Field(ge=0, le=1.5)
    temperatura: float = Field(ge=-10, le=50)
    viento: float = Field(ge=0, le=40)
    estilo: Literal["normal", "facil"] = "normal"
    idioma: Literal["es", "en"] = "es"


@app.get("/health")
def health():
    return {"ok": True, "mae": modelo.mae, "distritos": modelo.distritos}


@app.post("/predict")
def predict(e: Entrada):
    if e.distrito not in modelo.distritos:
        raise HTTPException(404, f"Distrito desconocido. Opciones: {modelo.distritos}")
    pred = modelo.predecir(e.distrito, e.hora, e.dia_semana, e.trafico, e.temperatura, e.viento)
    pred["explicacion"] = explicar(pred, e.estilo, e.idioma)
    return pred


@app.get("/anomalies")
def anomalies(n: int = 20):
    return modelo.anomalias(n)


@app.get("/stats")
def stats():
    return {"distritos": modelo.resumen_distritos(), "perfil_horario": modelo.perfil_horario(),
            "importancias": modelo.importancias(), "mae": modelo.mae}
