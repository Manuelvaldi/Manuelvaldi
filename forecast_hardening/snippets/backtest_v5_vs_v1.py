# ==============================================================================
# BACKTEST V1 vs V5 con las CLASES REALES del pipeline (ForecastProducto / ForecastProductoV5)
# Pegar en una celda DESPUES de ejecutar las celdas que definen las clases (V1..V5) y cargan
# mau_app / gpv_app / etc. No escribe nada en BigQuery ni toca los .pkl de produccion.
# Hiperparametros FIJOS (los que salieron ganadores en tus corridas) => no hay grilla ni pkl:
#   V1 = modelo de la clase base: todas las filas (incl. ceros de relleno), target crudo, sin lags.
#   V5 = modelo de produccion: solo dias reales, log1p, + lag_mau_mes_anterior / ma_3m_mes_anterior.
# ==============================================================================
import numpy as np, pandas as pd, xgboost as xgb
from sklearn.compose import TransformedTargetRegressor

PARAMS_V1 = dict(n_estimators=1500, learning_rate=0.01, max_depth=4, min_child_weight=4, subsample=0.7,
                 colsample_bytree=0.7, objective="reg:squarederror", random_state=123, n_jobs=-1)
PARAMS_V5 = dict(n_estimators=500, learning_rate=0.1, max_depth=3, min_child_weight=4, subsample=0.8,
                 colsample_bytree=0.8, objective="reg:squarederror", random_state=123, n_jobs=-1)

VARIANTES = {   # nombre -> (clase, log1p, solo_dias_reales, params)
    "V1": (ForecastProducto,   False, False, PARAMS_V1),
    "V5": (ForecastProductoV5, True,  True,  PARAMS_V5),
}


def predecir_resto(cls, kpi_df, corte, fin_mes, log, solo_reales, params, train_ini="2024-01-01"):
    """Entrena con datos hasta `corte` (inclusive) y predice corte+1 .. fin_mes."""
    inicio = corte + pd.Timedelta(days=1)
    kw = {"holdout_dias": 30} if issubclass(cls, ForecastProductoV2) else {}
    f = cls(nombre_algoritmo="bt_tmp", meta=1, fechas_entrenamiento=(train_ini, str(corte.date())),
            fechas_proyeccion=(str(inicio.date()), str(inicio.replace(day=1).date()), str(fin_mes.date())),
            directorio=directorio_salida, **kw)
    f._preparar_datos(kpi_df.copy())
    d = f.kpi_dummies.copy()
    if solo_reales:
        d["_r"] = f.kpi_modelo["real"].values
        d = d[d["_r"] == 1].drop(columns="_r")
    X, y = d.drop(columns=["target_kpi", "fecha"]), d["target_kpi"].clip(lower=0)
    m = xgb.XGBRegressor(**params)
    if log:
        m = TransformedTargetRegressor(regressor=m, func=np.log1p, inverse_func=np.expm1)
    m.fit(X, y)
    test = f.kpi_merge[(f.kpi_merge["fecha"] >= inicio) & (f.kpi_merge["fecha"] <= fin_mes)]
    Xt = pd.get_dummies(test).drop(columns=["fecha", "target_kpi", "real"], errors="ignore").reindex(columns=X.columns, fill_value=0)
    return pd.Series(np.maximum(m.predict(Xt), 0.0), index=pd.to_datetime(test["fecha"].values))


def backtest_v1_v5(kpi_df, col_target, meses, cortes=(0, 2, 7, 14, 21)):
    """corte 0 = corrida del DIA 1 (datos hasta el ultimo dia del mes anterior)."""
    real = (kpi_df[kpi_df["real"] == 1].assign(fecha=lambda d: pd.to_datetime(d["fecha"]))
            .groupby("fecha")[col_target].sum())
    filas = []
    for mes in meses:
        ini = pd.Timestamp(mes).replace(day=1)
        fin = ini + pd.offsets.MonthEnd(0)
        mes_real = real.reindex(pd.date_range(ini, fin))
        if mes_real.isna().any():
            continue
        for c in cortes:
            corte = ini + pd.Timedelta(days=c - 1)
            mtd = float(mes_real[:corte].sum()) if c > 0 else 0.0
            restante = mes_real[mes_real.index > corte]
            for nombre, (cls, log, solo_reales, params) in VARIANTES.items():
                p = predecir_resto(cls, kpi_df, corte, fin, log, solo_reales, params).reindex(restante.index)
                landing = mtd + float(p.sum())
                pf = p * restante.sum() / p.sum() if p.sum() > 0 else p
                filas.append(dict(mes=str(ini.date())[:7], corte=c, modelo=nombre,
                                  real_mes=float(mes_real.sum()), landing=landing,
                                  ape_cierre=abs(landing - mes_real.sum()) / mes_real.sum(),
                                  sesgo=(landing - mes_real.sum()) / mes_real.sum(),
                                  mape_diario=float((abs(p - restante) / restante).mean()),
                                  mape_forma=float((abs(pf - restante) / restante).mean())))
    return pd.DataFrame(filas)


def resumen_v1_v5(bt, etiqueta=""):
    print(f"\n===== {etiqueta} =====")
    print(bt.pivot_table(index="corte", columns="modelo", values=["ape_cierre", "sesgo", "mape_diario", "mape_forma"],
                         aggfunc="median").round(4).to_string())
    j = bt.pivot_table(index=["mes", "corte"], columns="modelo", values="ape_cierre")
    print(f"V5 mejor que V1 en cierre: {(j['V5'] < j['V1']).mean():.0%} de {len(j)} casos | "
          f"mediana APE V1={j['V1'].median():.3%} V5={j['V5'].median():.3%}")


# ---------------------------- USO ----------------------------
# Ultimos 6 meses cerrados (ajusta). Cada KPI = (dataframe del pipeline, columna objetivo).
MESES = pd.period_range(end=pd.Timestamp.today().to_period("M") - 1, periods=6, freq="M").to_timestamp()
KPIS = {"mau_app": (mau_app, "mau"), "gpv_app": (gpv_app, "gpv")}      # agrega: "ob_tc_large": (ob_tc_large, "ob"), ...
RESULT = {}
for nombre, (df_k, col) in KPIS.items():
    RESULT[nombre] = backtest_v1_v5(df_k, col, MESES)
    resumen_v1_v5(RESULT[nombre], nombre)
