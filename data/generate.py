"""Genera datos sintéticos realistas: calidad del aire (NO2) por distrito y hora en Madrid.
Uso: python data/generate.py  -> crea data/sample.csv
Mañana: cambia DISTRITOS / la fórmula para adaptarlo al reto (movilidad, energía, residuos...).
"""
from pathlib import Path
import numpy as np
import pandas as pd

rng = np.random.default_rng(42)
DISTRITOS = {  # distrito: nivel base de tráfico (0-1)
    "Centro": 0.9, "Salamanca": 0.8, "Chamberí": 0.75, "Arganzuela": 0.7,
    "Tetuán": 0.65, "Moncloa": 0.5, "Vallecas": 0.55, "Hortaleza": 0.4,
}
fechas = pd.date_range("2026-07-01", "2026-09-30 23:00", freq="h")

filas = []
for d, base in DISTRITOS.items():
    for t in fechas:
        h, finde = t.hour, t.dayofweek >= 5
        hora_punta = 1.0 if h in (8, 9, 18, 19, 20) else 0.5 if 7 <= h <= 21 else 0.15
        trafico = base * hora_punta * (0.6 if finde else 1.0) * rng.uniform(0.8, 1.2)
        temp = 22 + 8 * np.sin((h - 9) / 24 * 2 * np.pi) + rng.normal(0, 2)
        viento = max(0, rng.gamma(2, 2))
        no2 = 15 + 70 * trafico - 2.5 * viento + 0.3 * temp + rng.normal(0, 5)
        if rng.random() < 0.003:  # anomalías (obras, incidentes) para el detector
            no2 += rng.uniform(40, 80)
        filas.append({
            "fecha": t, "distrito": d, "hora": h, "dia_semana": t.dayofweek,
            "trafico": round(trafico, 3), "temperatura": round(temp, 1),
            "viento": round(viento, 1), "no2": round(max(no2, 2), 1),
        })

out = Path(__file__).parent / "sample.csv"
pd.DataFrame(filas).to_csv(out, index=False)
print(f"OK: {len(filas)} filas -> {out}")
