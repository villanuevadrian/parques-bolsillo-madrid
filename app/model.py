"""Capa de decisión: ML (temperatura) + índice de déficit + optimizador de parques bolsillo.
- RandomForest: modelo sustituto que predice la temperatura superficial en ola de calor según verde,
  asfalto y densidad -> estima cuántos °C baja cada parque. Ligero (CPU, segundos) y explicable.
- Optimizador: problema de cobertura máxima con presupuesto (variante de la mochila).
  1) Voraz: añade el parque con mejor beneficio marginal / coste.  2) Recocido simulado que mejora
  la solución voraz con movimientos añadir/quitar/intercambiar y penaliza restricciones incumplidas.
"""
from math import exp
from pathlib import Path
import random

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

DATA = Path(__file__).resolve().parent.parent / "data"
FEATURES = ["pct_verde", "pct_asfalto", "densidad"]
RADIO_M = 300        # OMS Europa: espacio verde a <300 m de casa
RADIO_FRESCOR_M = 150  # alcance del efecto de enfriamiento de un parque pequeño (hipótesis)
CELDA_M = 100


class Modelo:
    def __init__(self):
        self.distritos = pd.read_csv(DATA / "distritos.csv")
        c = pd.read_csv(DATA / "celdas.csv")
        c["densidad"] = c["poblacion"] / c["poblacion"].max()
        c["vulnerables"] = c["poblacion"] * (c["pct_mayores"] + c["pct_menores"])
        self.celdas = c
        self.cand = pd.read_csv(DATA / "candidatos.csv").set_index("id", drop=False)

        X, y = c[FEATURES], c["temp_verano"]
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
        self.reg = RandomForestRegressor(n_estimators=120, max_depth=10, n_jobs=-1, random_state=0)
        self.reg.fit(Xtr, ytr)
        self.mae = round(mean_absolute_error(yte, self.reg.predict(Xte)), 2)

        # Índice de déficit verde por celda (0-1): lejanía al verde x calor x vulnerabilidad
        lejania = np.clip(c["dist_verde_m"] / 600, 0, 1)
        calor = (c["temp_verano"] - c["temp_verano"].min()) / (c["temp_verano"].max() - c["temp_verano"].min())
        c["indice_deficit"] = (0.45 * lejania + 0.30 * calor + 0.25 * c["vulnerabilidad"]).round(3)

        # Precalcula qué celdas cubre y enfría cada candidato
        xy = c[["x", "y"]].to_numpy()
        self.cubre, self.enfria = {}, {}
        for i, k in self.cand.iterrows():
            d = np.hypot(xy[:, 0] - k["x"], xy[:, 1] - k["y"]) * CELDA_M
            self.cubre[i] = np.where(d <= RADIO_M)[0]
            self.enfria[i] = np.where(d <= RADIO_FRESCOR_M)[0]
        self.delta_temp = {i: self._delta_temp(i) for i in self.cand.index}

    # ---------- ML ----------
    def _delta_temp(self, i: int) -> float:
        """°C que baja de media en las celdas cercanas si se construye el parque i (modelo sustituto)."""
        cel = self.celdas.iloc[self.enfria[i]]
        antes = self.reg.predict(cel[FEATURES])
        extra = min(self.cand.loc[i, "m2"] / (CELDA_M * CELDA_M), 0.15)  # % de verde añadido
        despues_X = cel[FEATURES].assign(pct_verde=cel["pct_verde"] + extra,
                                         pct_asfalto=np.clip(cel["pct_asfalto"] - extra, 0, 1))
        return round(float(np.mean(antes - self.reg.predict(despues_X))), 2)

    def importancias(self) -> dict:
        return dict(sorted(((f, round(float(v), 3)) for f, v in zip(FEATURES, self.reg.feature_importances_)),
                           key=lambda x: -x[1]))

    # ---------- Evaluación de una cartera de parques ----------
    def _sin_cobertura(self) -> np.ndarray:
        return (self.celdas["dist_verde_m"] > RADIO_M).to_numpy()

    def evaluar(self, sel: list[int], pesos: dict) -> dict:
        c = self.celdas
        sin = self._sin_cobertura()
        nuevas = np.zeros(len(c), bool)
        for i in sel:
            nuevas[self.cubre[i]] = True
        nuevas &= sin
        vul_cub = float((c["vulnerables"] * nuevas).sum())
        pob_cub = float((c["poblacion"] * nuevas).sum())
        equidad = float((c["vulnerables"] * c["vulnerabilidad"] * nuevas).sum())
        frescor = sum(self.delta_temp[i] * c["poblacion"].iloc[self.enfria[i]].sum() for i in sel)
        valor = pesos["cobertura"] * vul_cub + pesos["equidad"] * equidad + pesos["calor"] * frescor / 2
        return {"valor": valor, "vulnerables_cubiertos": vul_cub, "poblacion_cubierta": pob_cub}

    def restricciones(self, sel: list[int], lim: dict) -> dict:
        k = self.cand.loc[sel] if sel else self.cand.iloc[0:0]
        coste = int(k["coste"].sum())
        en_vulnerables = k.loc[k["barrio"].map(self._vul_barrio()) >= 0.65, "coste"].sum()
        pct_eq = round(100 * en_vulnerables / coste, 1) if coste else 0.0
        r = {
            "presupuesto": {"valor": coste, "limite": lim["presupuesto"], "ok": coste <= lim["presupuesto"]},
            "plazas_aparcamiento": {"valor": int(k["plazas_perdidas"].sum()), "limite": lim["max_plazas"],
                                    "ok": k["plazas_perdidas"].sum() <= lim["max_plazas"]},
            "mantenimiento_anual": {"valor": int(k["mantenimiento_anual"].sum()), "limite": lim["max_mantenimiento"],
                                    "ok": k["mantenimiento_anual"].sum() <= lim["max_mantenimiento"]},
            "equidad_pct_inversion": {"valor": pct_eq, "limite": lim["min_equidad_pct"],
                                      "ok": pct_eq >= lim["min_equidad_pct"] or not sel},
        }
        return {n: {"valor": float(x["valor"]), "limite": float(x["limite"]), "ok": bool(x["ok"])} for n, x in r.items()}

    def _vul_barrio(self) -> dict:
        return self.celdas.groupby("barrio")["vulnerabilidad"].first().to_dict()

    def _objetivo(self, sel, pesos, lim) -> float:
        """Valor penalizado: las restricciones blandas restan, el presupuesto es duro."""
        r = self.restricciones(sel, lim)
        if not r["presupuesto"]["ok"]:
            return -1e12
        v = self.evaluar(sel, pesos)["valor"]
        fallos = sum(not x["ok"] for n, x in r.items() if n != "presupuesto")
        return v * (1 - 0.3 * fallos)

    # ---------- Optimizadores ----------
    def voraz(self, pesos, lim) -> list[int]:
        sel, restantes = [], set(self.cand.index)
        while True:
            base = self._objetivo(sel, pesos, lim)
            mejor, ratio = None, 0.0
            for i in restantes:
                g = self._objetivo(sel + [i], pesos, lim) - base
                if g > 0 and g / self.cand.loc[i, "coste"] > ratio:
                    mejor, ratio = i, g / self.cand.loc[i, "coste"]
            if mejor is None:
                return sel
            sel.append(mejor); restantes.discard(mejor)

    def recocido(self, inicio: list[int], pesos, lim, iters: int = 1500, semilla: int = 0) -> list[int]:
        rnd = random.Random(semilla)
        todos = list(self.cand.index)
        act, f_act = list(inicio), self._objetivo(inicio, pesos, lim)
        mejor, f_mejor = list(act), f_act
        T0 = max(abs(f_act), 1) * 0.05
        for t in range(iters):
            T = T0 * (1 - t / iters) + 1e-9
            nuevo = list(act)
            mov = rnd.random()
            fuera = [i for i in todos if i not in nuevo]
            if mov < 0.4 and fuera:
                nuevo.append(rnd.choice(fuera))
            elif mov < 0.6 and nuevo:
                nuevo.remove(rnd.choice(nuevo))
            elif nuevo and fuera:
                nuevo[rnd.randrange(len(nuevo))] = rnd.choice(fuera)
            f = self._objetivo(nuevo, pesos, lim)
            if f >= f_act or rnd.random() < exp((f - f_act) / T):
                act, f_act = nuevo, f
                if f > f_mejor:
                    mejor, f_mejor = list(nuevo), f
        return mejor

    def optimizar(self, lim: dict, pesos: dict) -> dict:
        g = self.voraz(pesos, lim)
        s = self.recocido(g, pesos, lim)
        fg, fs = self._objetivo(g, pesos, lim), self._objetivo(s, pesos, lim)
        if fs < fg:
            s, fs = g, fg
        return {
            "seleccion": self.detalle(s),
            "kpis_antes": self.kpis([]), "kpis_despues": self.kpis(s),
            "restricciones": self.restricciones(s, lim),
            "comparativa": {"voraz": round(fg), "recocido": round(fs),
                            "mejora_pct": round(float(100 * (fs - fg) / fg), 1) if fg > 0 else 0.0},
        }

    # ---------- Salidas ----------
    def kpis(self, sel: list[int]) -> dict:
        c = self.celdas
        cub = ~self._sin_cobertura()
        for i in sel:
            cub[self.cubre[i]] = True
        k = self.cand.loc[sel] if sel else self.cand.iloc[0:0]
        verde_m2 = float(self.distritos.loc[self.distritos["distrito"] == "Tetuán", "m2_verde"].iloc[0]) + k["m2"].sum()
        return {
            "pct_vulnerables_300m": round(100 * (c["vulnerables"] * cub).sum() / c["vulnerables"].sum(), 1),
            "pct_poblacion_300m": round(100 * (c["poblacion"] * cub).sum() / c["poblacion"].sum(), 1),
            "m2_verde_hab": round(verde_m2 / c["poblacion"].sum(), 2),
            "personas_refrescadas": int(sum(c["poblacion"].iloc[self.enfria[i]].sum() for i in sel)),
            "inversion": int(k["coste"].sum()),
            "parques": len(sel),
        }

    def detalle(self, sel: list[int]) -> list[dict]:
        c, sin = self.celdas, self._sin_cobertura()
        out = []
        for i in sel:
            k = self.cand.loc[i].to_dict()
            idx = [j for j in self.cubre[i] if sin[j]]
            k.update({
                "nuevos_vecinos_300m": int(c["poblacion"].iloc[idx].sum()),
                "nuevos_vulnerables_300m": int(c["vulnerables"].iloc[idx].sum()),
                "bajada_temp_c": self.delta_temp[i],
                "coste_por_vecino": round(k["coste"] / max(c["poblacion"].iloc[idx].sum(), 1), 1),
            })
            out.append({kk: (v.item() if hasattr(v, "item") else v) for kk, v in k.items()})
        return sorted(out, key=lambda r: -r["nuevos_vulnerables_300m"])

    def diagnostico(self) -> list[dict]:
        cols = ["id", "lat", "lon", "barrio", "poblacion", "dist_verde_m", "temp_verano", "vulnerabilidad", "indice_deficit"]
        return self.celdas[cols].to_dict("records")

    def resumen_barrios(self) -> list[dict]:
        c = self.celdas.assign(sin=self._sin_cobertura())
        g = c.groupby("barrio").agg(poblacion=("poblacion", "sum"), vulnerabilidad=("vulnerabilidad", "first"),
                                     temp_media=("temp_verano", "mean"), deficit_medio=("indice_deficit", "mean"))
        g["pct_sin_verde_300m"] = c.groupby("barrio").apply(
            lambda b: 100 * (b["poblacion"] * b["sin"]).sum() / b["poblacion"].sum(), include_groups=False)
        return g.round(2).reset_index().sort_values("deficit_medio", ascending=False).to_dict("records")
