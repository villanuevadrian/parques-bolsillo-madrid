"""Capa de ML: predicción (RandomForest) + detección de anomalías (IsolationForest).
Ligero (CPU, segundos), explicable (importancia de variables) -> argumento de sostenibilidad.
"""
from pathlib import Path
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import train_test_split

DATA = Path(__file__).resolve().parent.parent / "data" / "sample.csv"
FEATURES = ["hora", "dia_semana", "trafico", "temperatura", "viento", "distrito_cod"]
TARGET = "no2"
UMBRAL_ALERTA = 40  # µg/m3, referencia UE media anual NO2


class Modelo:
    def __init__(self):
        df = pd.read_csv(DATA, parse_dates=["fecha"])
        self.distritos = sorted(df["distrito"].unique())
        df["distrito_cod"] = df["distrito"].map({d: i for i, d in enumerate(self.distritos)})
        self.df = df

        X, y = df[FEATURES], df[TARGET]
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=0)
        self.reg = RandomForestRegressor(n_estimators=80, max_depth=12, n_jobs=-1, random_state=0)
        self.reg.fit(Xtr, ytr)
        self.mae = round(mean_absolute_error(yte, self.reg.predict(Xte)), 2)

        self.iso = IsolationForest(contamination=0.005, random_state=0)
        self.df["anomalia"] = self.iso.fit_predict(df[FEATURES + [TARGET]]) == -1

    def predecir(self, distrito: str, hora: int, dia_semana: int,
                 trafico: float, temperatura: float, viento: float) -> dict:
        fila = pd.DataFrame([{
            "hora": hora, "dia_semana": dia_semana, "trafico": trafico,
            "temperatura": temperatura, "viento": viento,
            "distrito_cod": self.distritos.index(distrito),
        }])
        valor = round(float(self.reg.predict(fila)[0]), 1)
        return {
            "distrito": distrito, "no2_predicho": valor,
            "nivel": "alto" if valor > UMBRAL_ALERTA * 1.5 else "moderado" if valor > UMBRAL_ALERTA else "bueno",
            "factores": self.importancias(),
            "error_medio_modelo": self.mae,
        }

    def importancias(self) -> dict:
        return dict(sorted(
            ((f, round(float(i), 3)) for f, i in zip(FEATURES, self.reg.feature_importances_)),
            key=lambda x: -x[1]))

    def anomalias(self, n: int = 20) -> list[dict]:
        a = self.df[self.df["anomalia"]].sort_values(TARGET, ascending=False).head(n)
        a = a.assign(fecha=a["fecha"].astype(str))
        return a[["fecha", "distrito", "no2", "trafico", "viento"]].to_dict("records")

    def resumen_distritos(self) -> list[dict]:
        g = self.df.groupby("distrito")[TARGET].agg(["mean", "max"]).round(1).reset_index()
        return g.rename(columns={"mean": "no2_medio", "max": "no2_max"}).to_dict("records")

    def perfil_horario(self) -> list[dict]:
        return self.df.groupby("hora")[TARGET].mean().round(1).reset_index().to_dict("records")
