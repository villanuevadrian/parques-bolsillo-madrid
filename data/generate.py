"""Prepara los datos. Uso: python data/generate.py
REALES (datos.madrid.es, en data/raw/):
  - Superficie de zonas verdes por distrito 2025 (dataset 300266)
  - Población por distrito y barrio a 1-ene-2026 (dataset 300557)
  - Ranking de vulnerabilidad de distritos y barrios 2020 (dataset 300301)
Límites oficiales de barrios (geoportal.madrid.es, TopoJSON).
SINTÉTICOS (calibrados con los reales): cuadrícula de 100 m recortada a la silueta real de Tetuán con población por
barrio real, edades, temperatura, verde existente y solares candidatos para parques bolsillo.
Salidas: data/distritos.csv, data/celdas.csv, data/candidatos.csv
"""
from pathlib import Path
import json
import unicodedata

import numpy as np
import pandas as pd

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent
rng = np.random.default_rng(42)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().upper().strip()
    return s.replace(" - ", "-").split("-")[0].strip()  # "SAN BLAS-CANILLEJAS" -> "SAN BLAS"


# ---------- 1. Diagnóstico de ciudad: 100% datos reales ----------
pob = pd.read_csv(RAW / "poblacion_distrito_barrio.csv", sep=";", encoding="utf-8-sig", thousands=".")
pob = pob[pob["fecha"] == "1 de enero de 2026"]
verde = pd.read_csv(RAW / "zonas_verdes_distritos_2025.csv", sep=";", encoding="utf-8-sig",
                    decimal=",", thousands=".").dropna(subset=["DISTRITO"])
verde = verde.rename(columns={verde.columns[2]: "m2_verde"})
vul_d = pd.read_csv(RAW / "vulnerabilidad_1.csv", sep=";", encoding="latin1", decimal=",")
vul_d = vul_d[vul_d["Año"] == 2020]
vul_b = pd.read_csv(RAW / "vulnerabilidad_0.csv", sep=";", encoding="latin1", decimal=",")
vul_b = vul_b[vul_b["Año"] == 2020]

d = pob.groupby("distrito", as_index=False)["num_personas"].sum()
d["distrito"] = d["distrito"].str.strip()
d["k"] = d["distrito"].map(norm)
verde["k"] = verde["DISTRITO"].map(norm)
vul_d["k"] = vul_d["Distrito"].str.split(". ", n=1, regex=False).str[1].map(norm)
d = d.merge(verde[["k", "m2_verde"]], on="k").merge(vul_d[["k", "Ranking"]], on="k")
d = d.rename(columns={"num_personas": "poblacion", "Ranking": "ranking_vulnerabilidad"}).drop(columns="k")
d["m2_hab"] = (d["m2_verde"] / d["poblacion"]).round(2)
d["m2_verde"] = d["m2_verde"].round(0)
d.sort_values("m2_hab").to_csv(OUT / "distritos.csv", index=False)

# ---------- 1b. Detección de barrios: 131 barrios, 100% datos reales ----------
# El verde solo se publica por distrito: cada barrio hereda el m²/hab de su distrito.
vb_all = vul_b.copy()
vb_all["cod_barrio"] = vb_all["BARRIO"].str.strip().str.split(".", n=1, regex=False).str[0].astype(int)
b = pob[["cod_distrito", "distrito", "cod_barrio", "barrio", "num_personas"]].copy()
b[["distrito", "barrio"]] = b[["distrito", "barrio"]].apply(lambda s: s.str.strip())
b = b.merge(vb_all[["cod_barrio", "Ranking"]], on="cod_barrio", how="left")
b = b.merge(d[["distrito", "m2_hab"]], on="distrito", how="left")
b = b.rename(columns={"num_personas": "poblacion", "Ranking": "ranking_vulnerabilidad", "m2_hab": "m2_hab_distrito"})
vul_norm = 1 - (b["ranking_vulnerabilidad"] - 1) / 130            # 1 = el más vulnerable
verde_norm = 1 - b["m2_hab_distrito"] / b["m2_hab_distrito"].max()  # 1 = el que menos verde tiene
b["prioridad"] = (0.6 * vul_norm + 0.4 * verde_norm).round(3)
b = b.dropna(subset=["prioridad"]).sort_values("prioridad", ascending=False)
b["puesto"] = range(1, len(b) + 1)
b.to_csv(OUT / "barrios.csv", index=False)

# ---------- 2. Tetuán: cuadrícula sintética de 100 m calibrada ----------
COD_TETUAN = 6
barrios = pob[pob["cod_distrito"] == COD_TETUAN][["barrio", "num_personas"]].copy()
barrios["barrio"] = barrios["barrio"].str.strip()
vb = vul_b[vul_b["DISTRITO"].str.contains("Tetu")].copy()
vb["barrio"] = vb["BARRIO"].str.split(". ", n=1, regex=False).str[1].str.strip()
barrios = barrios.merge(vb[["barrio", "Ranking"]], on="barrio")
barrios["vulnerabilidad"] = (1 - (barrios["Ranking"] - 1) / 130).round(3)  # 1 = barrio más vulnerable de Madrid

CELDA, ANILLO_M = 100, 300
# Límites oficiales de barrios (geoportal.madrid.es, TopoJSON en lon/lat cuantizado)
topo = json.loads((RAW / "barrios_topo.json").read_text(encoding="utf-8"))
sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
arcos = []
for a in topo["arcs"]:  # decodifica arcos con codificación delta
    q = np.cumsum(np.array(a, dtype=float), axis=0)
    arcos.append(np.column_stack([q[:, 0] * sc[0] + tr[0], q[:, 1] * sc[1] + tr[1]]))


def anillo(idx_arcos):
    pts = [arcos[i] if i >= 0 else arcos[~i][::-1] for i in idx_arcos]
    return np.vstack(pts)


POLIS = {}  # nombre barrio -> (distrito, [anillos exteriores lon/lat])
for g in topo["objects"]["Barrios"]["geometries"]:
    partes = g["arcs"] if g["type"] == "Polygon" else [r for poly in g["arcs"] for r in poly[:1]]
    if g["type"] == "Polygon":
        partes = partes[:1]  # anillo exterior
    POLIS[g["properties"]["NOMBRE"].strip()] = (g["properties"]["NOMDIS"].strip(), [anillo(r) for r in partes])


def dentro(lon, lat, poly):
    """Punto en polígono (ray casting vectorizado)."""
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cruza = ((y[None] > lat[:, None]) != (y2[None] > lat[:, None])) & (
        lon[:, None] < (x2 - x)[None] * (lat[:, None] - y[None]) / ((y2 - y)[None] + 1e-15) + x[None])
    return cruza.sum(axis=1) % 2 == 1


tetuan = {n: v for n, v in POLIS.items() if v[0] == "Tetuán"}
pts = np.vstack([r for _, rs in tetuan.values() for r in rs])
LON0, LAT0 = pts[:, 0].min(), pts[:, 1].min()
M_LON, M_LAT = 84_500, 111_000  # metros por grado a 40,46° N
mx = (pts[:, 0].max() - LON0) * M_LON + 2 * ANILLO_M
my = (pts[:, 1].max() - LAT0) * M_LAT + 2 * ANILLO_M
xs, ys = np.meshgrid(np.arange(0, mx, CELDA) - ANILLO_M, np.arange(0, my, CELDA) - ANILLO_M)
g_lon = LON0 + xs.ravel() / M_LON
g_lat = LAT0 + ys.ravel() / M_LAT
barrio = np.full(len(g_lon), None, dtype=object)
for n, (_, rs) in POLIS.items():
    for r in rs:
        m = (barrio == None) & dentro(g_lon, g_lat, r)  # noqa: E711
        barrio[m] = n
es_tetuan = np.isin(barrio, list(tetuan))
gx, gy = xs.ravel() / CELDA, ys.ravel() / CELDA  # coordenadas en celdas de 100 m
txy = np.column_stack([gx[es_tetuan], gy[es_tetuan]])
d_tet = np.array([np.min(np.hypot(txy[:, 0] - a, txy[:, 1] - b)) for a, b in zip(gx, gy)]) * CELDA
en_anillo = ~es_tetuan & (d_tet <= ANILLO_M)

# Zonas verdes existentes: (nombre, lat, lon, radio m). Posiciones aproximadas, incluidas las de distritos
# vecinos: para un vecino cuenta la distancia real al parque, no el límite administrativo.
PARQUES = [
    ("Parque Agustín Rodríguez Sahagún (Tetuán)", 40.4762, -3.7088, 230),
    ("Dehesa de la Villa (Moncloa-Aravaca)", 40.4635, -3.7165, 450),
    ("Parque del Canal de Isabel II (Chamberí)", 40.4452, -3.7055, 200),
    ("Parque Norte (Fuencarral-El Pardo)", 40.4835, -3.7030, 220),
    ("Plaza ajardinada (Tetuán, sintética)", 40.4595, -3.6985, 60),
    ("Plaza ajardinada (Tetuán, sintética)", 40.4680, -3.6950, 60),
]
pd.DataFrame(PARQUES, columns=["nombre", "lat", "lon", "radio_m"]).to_csv(OUT / "parques_existentes.csv", index=False)
dist_verde = np.min([np.hypot((g_lon - lo) * M_LON, (g_lat - la) * M_LAT) - r for _, la, lo, r in PARQUES], axis=0)

pd.DataFrame({"lat": g_lat[en_anillo].round(6), "lon": g_lon[en_anillo].round(6),
              "barrio": barrio[en_anillo]}).to_csv(OUT / "anillo.csv", index=False)

c = pd.DataFrame({"x": gx[es_tetuan], "y": gy[es_tetuan], "barrio": barrio[es_tetuan],
                  "lat": g_lat[es_tetuan].round(6), "lon": g_lon[es_tetuan].round(6)})
c = c.merge(barrios[["barrio", "num_personas", "vulnerabilidad"]], on="barrio", how="left")
dv = dist_verde[es_tetuan]
c["es_verde"] = dv <= 0
c["dist_verde_m"] = np.clip(dv, 0, None).round(0)
c["pct_verde"] = np.where(c["es_verde"], rng.uniform(0.6, 0.9, len(c)), rng.beta(1.2, 12, len(c))).round(3)
c["pct_asfalto"] = np.clip(1 - c["pct_verde"] - rng.uniform(0.05, 0.25, len(c)), 0, 1).round(3)
peso = np.where(c["es_verde"], 0.02, rng.lognormal(0, 0.35, len(c)))  # población repartida sin parques
c["poblacion"] = 0.0
for b, total in barrios.set_index("barrio")["num_personas"].items():
    m = c["barrio"] == b
    c.loc[m, "poblacion"] = total * peso[m] / peso[m].sum()  # suma exacta = padrón real del barrio
c["poblacion"] = c["poblacion"].round(0).astype(int)
c["pct_mayores"] = np.clip(rng.normal(0.21, 0.05, len(c)) + 0.05 * c["vulnerabilidad"], 0.05, 0.45).round(3)
c["pct_menores"] = np.clip(rng.normal(0.11, 0.03, len(c)), 0.02, 0.25).round(3)
# Temperatura superficial en ola de calor (tipo satélite): más asfalto y densidad -> más calor
dens = c["poblacion"] / c["poblacion"].max()
c["temp_verano"] = (33 + 6 * c["pct_asfalto"] - 8 * c["pct_verde"] + 1.5 * dens
                    + rng.normal(0, 0.6, len(c))).round(1)
c["id"] = range(len(c))
c = c.drop(columns="num_personas")
c.to_csv(OUT / "celdas.csv", index=False)

# ---------- 3. Candidatos a parque bolsillo ----------
TIPOS = {  # tipo: (m2 min, m2 max, plazas de aparcamiento perdidas por 100 m2)
    "Solar municipal vacío": (300, 1500, 0),
    "Interior de manzana": (200, 800, 0),
    "Calle a pacificar": (250, 900, 1.5),
    "Patio escolar abierto en verano": (400, 1200, 0),
}
opciones = c[~c["es_verde"]].sample(45, random_state=1)
filas = []
for i, (_, o) in enumerate(opciones.iterrows()):
    tipo = rng.choice(list(TIPOS), p=[0.35, 0.25, 0.3, 0.1])
    lo, hi, plazas = TIPOS[tipo]
    m2 = int(rng.uniform(lo, hi))
    filas.append({
        "id": i, "celda": int(o["id"]), "x": o["x"], "y": o["y"], "lat": o["lat"], "lon": o["lon"],
        "barrio": o["barrio"], "tipo": tipo, "m2": m2,
        "coste": int(m2 * rng.uniform(150, 320) / 1000) * 1000,  # €/m2 de urbanización (hipótesis)
        "plazas_perdidas": int(round(m2 / 100 * plazas)),
        "mantenimiento_anual": int(m2 * rng.uniform(3, 6)),  # €/año
        "agua_m3_anual": int(m2 * rng.uniform(0.2, 0.6)),  # especies de bajo consumo (xerojardinería)
    })
pd.DataFrame(filas).to_csv(OUT / "candidatos.csv", index=False)

print(f"OK: {len(d)} distritos (reales), {len(c)} celdas Tetuán ({c['poblacion'].sum()} hab. = padrón real), "
      f"{len(filas)} candidatos")
