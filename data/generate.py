"""Prepara los datos. Uso: python data/generate.py
REALES (datos.madrid.es, en data/raw/):
  - Superficie de zonas verdes por distrito 2025 (dataset 300266)
  - Población por distrito y barrio a 1-ene-2026 (dataset 300557)
  - Ranking de vulnerabilidad de distritos y barrios 2020 (dataset 300301)
  - Límites oficiales de barrios (geoportal.madrid.es, TopoJSON)
  - Principales parques y jardines municipales con coordenadas (dataset 200761)
SINTÉTICOS (calibrados con los reales), para CADA distrito: cuadrícula de 100 m recortada a su silueta real, población
por barrio real, edades, temperatura y solares candidatos para parques bolsillo.
Salidas: data/distritos.csv, data/barrios.csv, data/parques_existentes.csv y data/distritos/<slug>/*.csv
"""
from pathlib import Path
import json
import unicodedata

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

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

# ---------- 2. Geometría oficial y parques existentes reales ----------
topo = json.loads((RAW / "barrios_topo.json").read_text(encoding="utf-8"))
sc, tr = topo["transform"]["scale"], topo["transform"]["translate"]
arcos = []
for a in topo["arcs"]:  # decodifica arcos con codificación delta (lon/lat cuantizado)
    q = np.cumsum(np.array(a, dtype=float), axis=0)
    arcos.append(np.column_stack([q[:, 0] * sc[0] + tr[0], q[:, 1] * sc[1] + tr[1]]))


def anillo_poly(idx):
    return np.vstack([arcos[i] if i >= 0 else arcos[~i][::-1] for i in idx])


POLIS = []  # (cod_distrito, cod_barrio, nombre, polígono exterior lon/lat)
for g in topo["objects"]["Barrios"]["geometries"]:
    exteriores = [g["arcs"][0]] if g["type"] == "Polygon" else [poly[0] for poly in g["arcs"]]
    pr = g["properties"]
    for e in exteriores:
        POLIS.append((int(pr["CODDIS"]), int(pr["COD_BAR"]), pr["NOMBRE"].strip(), anillo_poly(e)))


def dentro(lon, lat, poly):
    """Punto en polígono (ray casting vectorizado)."""
    x, y = poly[:, 0], poly[:, 1]
    x2, y2 = np.roll(x, -1), np.roll(y, -1)
    cruza = ((y[None] > lat[:, None]) != (y2[None] > lat[:, None])) & (
        lon[:, None] < (x2 - x)[None] * (lat[:, None] - y[None]) / ((y2 - y)[None] + 1e-15) + x[None])
    return cruza.sum(axis=1) % 2 == 1


# Parques y jardines municipales con coordenadas reales. No traen superficie: radio aproximado según el tipo.
pj = json.loads((RAW / "parques_jardines.json").read_text(encoding="utf-8"))["@graph"]
PARQUES = pd.DataFrame([{
    "nombre": x["title"].strip(), "lat": x["location"]["latitude"], "lon": x["location"]["longitude"],
    "radio_m": 150 if x["title"].lower().startswith(("parque", "dehesa", "casa de campo", "monte")) else 50,
} for x in pj if "location" in x])
PARQUES.to_csv(OUT / "parques_existentes.csv", index=False)

CELDA, ANILLO_M = 100, 300
M_LON, M_LAT = 84_500, 111_000  # metros por grado a ~40,4° N
TIPOS = {  # tipo: (m2 min, m2 max, plazas de aparcamiento perdidas por 100 m2)
    "Solar municipal vacío": (300, 1500, 0),
    "Interior de manzana": (200, 800, 0),
    "Calle a pacificar": (250, 900, 1.5),
    "Patio escolar abierto en verano": (400, 1200, 0),
}


def slug(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace(" ", "_").replace("-", "_")


def generar_distrito(cod: int, nombre: str):
    rng = np.random.default_rng(cod)
    mios = [x for x in POLIS if x[0] == cod]
    pts = np.vstack([x[3] for x in mios])
    lon0, lat0 = pts[:, 0].min(), pts[:, 1].min()
    mx = (pts[:, 0].max() - lon0) * M_LON + 2 * ANILLO_M
    my = (pts[:, 1].max() - lat0) * M_LAT + 2 * ANILLO_M
    xs, ys = np.meshgrid(np.arange(0, mx, CELDA) - ANILLO_M, np.arange(0, my, CELDA) - ANILLO_M)
    g_lon, g_lat = lon0 + xs.ravel() / M_LON, lat0 + ys.ravel() / M_LAT
    cod_b = np.zeros(len(g_lon), int)
    nom_b = np.full(len(g_lon), None, dtype=object)
    caja = (lon0 - 0.01, lat0 - 0.01, pts[:, 0].max() + 0.01, pts[:, 1].max() + 0.01)
    for cd, cb, nb, poly in POLIS:
        if poly[:, 0].max() < caja[0] or poly[:, 0].min() > caja[2] or poly[:, 1].max() < caja[1] or poly[:, 1].min() > caja[3]:
            continue
        m = (cod_b == 0) & dentro(g_lon, g_lat, poly)
        cod_b[m], nom_b[m] = cb, nb
    mio = (cod_b // 10 == cod) & (cod_b > 0)
    gx, gy = xs.ravel() / CELDA, ys.ravel() / CELDA
    d_mio, _ = cKDTree(np.column_stack([gx[mio], gy[mio]])).query(np.column_stack([gx, gy]))
    en_anillo = ~mio & (d_mio * CELDA <= ANILLO_M)

    # Distancia al parque real más cercano, sea del distrito que sea
    pxy = np.column_stack([(PARQUES["lon"] - lon0) * M_LON, (PARQUES["lat"] - lat0) * M_LAT])
    cxy = np.column_stack([(g_lon - lon0) * M_LON, (g_lat - lat0) * M_LAT])
    dd = np.hypot(cxy[:, None, 0] - pxy[None, :, 0], cxy[:, None, 1] - pxy[None, :, 1]) - PARQUES["radio_m"].values[None]
    dist_verde = dd.min(axis=1)

    dist_dir = OUT / "distritos" / slug(nombre)
    dist_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"lat": g_lat[en_anillo].round(6), "lon": g_lon[en_anillo].round(6),
                  "barrio": nom_b[en_anillo]}).to_csv(dist_dir / "anillo.csv", index=False)

    bar = b[b["cod_distrito"] == cod][["cod_barrio", "barrio", "poblacion", "ranking_vulnerabilidad"]].copy()
    bar["vulnerabilidad"] = (1 - (bar["ranking_vulnerabilidad"] - 1) / 130).round(3)
    c = pd.DataFrame({"x": gx[mio], "y": gy[mio], "cod_barrio": cod_b[mio],
                      "lat": g_lat[mio].round(6), "lon": g_lon[mio].round(6)})
    c = c.merge(bar[["cod_barrio", "barrio", "poblacion", "vulnerabilidad"]], on="cod_barrio", how="inner")
    c = c.rename(columns={"poblacion": "pob_barrio"})
    dv = dist_verde[mio][: len(c)] if len(c) == mio.sum() else None
    c["dist_raw"] = pd.Series(dist_verde[mio]).iloc[: len(c)].values if dv is None else dv
    c["es_verde"] = c["dist_raw"] <= 0
    c["dist_verde_m"] = np.clip(c["dist_raw"], 0, None).round(0)
    c["pct_verde"] = np.where(c["es_verde"], rng.uniform(0.6, 0.9, len(c)), rng.beta(1.2, 12, len(c))).round(3)
    c["pct_asfalto"] = np.clip(1 - c["pct_verde"] - rng.uniform(0.05, 0.25, len(c)), 0, 1).round(3)
    peso = np.where(c["es_verde"], 0.02, rng.lognormal(0, 0.35, len(c)))
    c["poblacion"] = 0.0
    for cb, grupo in c.groupby("cod_barrio"):
        c.loc[grupo.index, "poblacion"] = grupo["pob_barrio"] * peso[grupo.index] / peso[grupo.index].sum()
    c["poblacion"] = c["poblacion"].round(0).astype(int)  # suma = padrón real del barrio
    c["pct_mayores"] = np.clip(rng.normal(0.21, 0.05, len(c)) + 0.05 * c["vulnerabilidad"], 0.05, 0.45).round(3)
    c["pct_menores"] = np.clip(rng.normal(0.11, 0.03, len(c)), 0.02, 0.25).round(3)
    dens = c["poblacion"] / c["poblacion"].max()
    c["temp_verano"] = (33 + 6 * c["pct_asfalto"] - 8 * c["pct_verde"] + 1.5 * dens
                        + rng.normal(0, 0.6, len(c))).round(1)
    c["id"] = range(len(c))
    c = c.drop(columns=["pob_barrio", "dist_raw", "cod_barrio"])
    c.to_csv(dist_dir / "celdas.csv", index=False)

    n_cand = int(np.clip(c["poblacion"].sum() / 4000, 30, 70))
    opciones = c[~c["es_verde"] & (c["poblacion"] > 0)].sample(n_cand, random_state=1)
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
    pd.DataFrame(filas).to_csv(dist_dir / "candidatos.csv", index=False)
    return len(c), int(c["poblacion"].sum()), len(filas)


if __name__ == "__main__":
    import sys
    import time
    cods = pob.groupby("cod_distrito")["distrito"].first().str.strip()
    solo = set(sys.argv[1:])
    for cod, nombre in cods.items():
        if solo and slug(nombre) not in solo:
            continue
        t = time.time()
        n, p_, k = generar_distrito(int(cod), nombre)
        print(f"  {nombre}: {n} celdas, {p_} hab., {k} candidatos ({time.time() - t:.1f} s)")
    print(f"OK: {len(d)} distritos y {len(b)} barrios (reales), {len(PARQUES)} parques oficiales")
