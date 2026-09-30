"""Pruebas de los parches de lógica de V12, cargando el código DESDE el notebook V12."""
import os
import pickle
from pathlib import Path

import nbformat
import numpy as np
import pandas as pd
import pytest

NB = Path(os.environ.get("V12_NOTEBOOK", Path(__file__).resolve().parents[1] / "Script_Diario_V12_blindado.ipynb"))


@pytest.fixture(scope="module")
def cells():
    return [c.source for c in nbformat.read(NB, as_version=4).cells if c.cell_type == "code"]


def _find(cells, needle, nth=0):
    hits = [s for s in cells if needle in s]
    assert len(hits) > nth, needle
    return hits[nth]


def _helper_ns(cells):
    src = _find(cells, "V12 — BLINDAJE")
    ns = {"__name__": "helper"}
    exec(compile(src, "<helper>", "exec"), ns)
    return ns


def test_reloj_chile_no_salta_de_dia_por_utc(cells, world, monkeypatch):
    monkeypatch.setenv("PIPELINE_NOW", "2026-09-30 21:30")
    ns = _helper_ns(cells)
    assert ns["hoy_chile"]() == pd.Timestamp("2026-09-30")            # en UTC ya sería 1-oct
    assert ns["ahora_utc_naive"]() == pd.Timestamp("2026-10-01 00:30")


def test_fixes_se_apagan_por_env(cells, world, monkeypatch):
    monkeypatch.setenv("PIPELINE_V12_OFF", "lag_mes_sin_datos")
    ns = _helper_ns(cells)
    assert ns["V12_FIXES"]["lag_mes_sin_datos"] is False and ns["V12_FIXES"]["tmc_anios"] is True


def test_pickle_atomico_conserva_el_anterior_si_falla(cells, world, tmp_path):
    ns = _helper_ns(cells)
    f = tmp_path / "m.pkl"
    ns["_dump_pickle_atomic"]({"ok": 1}, str(f))
    assert pickle.load(open(f, "rb")) == {"ok": 1}

    class Boom:
        def __reduce__(self):
            raise RuntimeError("corte a mitad de dump")

    with pytest.raises(RuntimeError):
        ns["_dump_pickle_atomic"](Boom(), str(f))
    assert pickle.load(open(f, "rb")) == {"ok": 1}                    # el modelo bueno sigue ahí
    assert [p.name for p in tmp_path.iterdir()] == ["m.pkl"]          # sin .tmp huérfanos


def test_columnas_del_modelo_grid_y_transformed(cells, world):
    from sklearn.compose import TransformedTargetRegressor
    from sklearn.model_selection import GridSearchCV
    from xgboost import XGBRegressor
    ns = _helper_ns(cells)
    X = pd.DataFrame({"a": np.arange(50.0), "b": np.arange(50.0) ** 2})
    y = X["a"] * 2 + 1
    g = GridSearchCV(XGBRegressor(n_estimators=5), {"max_depth": [2]}, cv=2).fit(X, y)
    assert ns["_columnas_del_modelo"](g) == ["a", "b"]
    t = TransformedTargetRegressor(regressor=XGBRegressor(n_estimators=5), func=np.log1p, inverse_func=np.expm1).fit(X, y)
    assert ns["_columnas_del_modelo"](t) == ["a", "b"]
    assert ns["_columnas_del_modelo"](object()) is None


def _v5_namespace(cells, fix_on):
    ns = {"__name__": "v5"}
    exec("import pandas as pd, numpy as np, pickle, xgboost as xgb\n"
         "from sklearn.model_selection import train_test_split, GridSearchCV, TimeSeriesSplit\n"
         "from sklearn.metrics import mean_absolute_percentage_error\n"
         "from sklearn.compose import TransformedTargetRegressor\nfrom sklearn.base import clone\n", ns)
    ns["V12_FIXES"] = {"lag_mes_sin_datos": fix_on}
    ns["_dump_pickle_atomic"] = lambda o, p: pickle.dump(o, open(p, "wb"))
    ns["_columnas_del_modelo"] = lambda m: None
    # la clase base vigente es la ÚLTIMA definición (celda 'ForecastProductoV2' en adelante la hereda)
    for needle in ("class ForecastProducto:", "class ForecastProductoV2", "class ForecastProductoV3",
                   "class ForecastProductoV4", "class ForecastProductoV5"):
        src = [s for s in cells if needle in s][-1]
        exec(compile(src, "<cls>", "exec"), ns)
    return ns


def _serie(hasta):
    idx = pd.date_range("2024-01-01", hasta, freq="D")
    rng = np.random.default_rng(1)
    v = 1000 + 10 * np.arange(len(idx)) + 50 * rng.standard_normal(len(idx))
    return pd.DataFrame({"fecha": idx, "dia_semana": "x", "dia": idx.day, "mes": idx.month, "year": idx.year,
                         "real": 1, "gpv": v})


def _kpi_merge(ns, hasta, tmp_path):
    from forecast_hardening.dryrun import stubs
    stubs.make_drive_files(pd.Timestamp("2026-10-01"), fresh_models=False)
    f = ns["ForecastProductoV5"]("gpv_app", 1, ("2024-01-01", hasta), ("2023-10-01", "2026-10-01", "2026-10-31"), str(tmp_path))
    f._preparar_datos(_serie(hasta))
    return f.kpi_merge.set_index("fecha")


def test_v5_lag_mes_sin_datos_hereda_el_ultimo_mes_observado(cells, world, tmp_path):
    off = _kpi_merge(_v5_namespace(cells, False), "2026-09-30", tmp_path)
    on = _kpi_merge(_v5_namespace(cells, True), "2026-09-30", tmp_path)
    oct_off, oct_on = off.loc["2026-10-05"], on.loc["2026-10-05"]
    assert oct_off["lag_mau_mes_anterior"] == 0 and oct_off["ma_3m_mes_anterior"] == 0       # bug V11
    sep = off.loc["2026-09-01":"2026-09-30"].query("real == 1")["target_kpi"].sum()
    assert oct_on["lag_mau_mes_anterior"] == pytest.approx(sep)
    ult3 = [off.loc[f"2026-{m:02d}-01":f"2026-{m:02d}-28"].query("real==1")["target_kpi"].sum() for m in (7, 8, 9)]
    assert oct_on["ma_3m_mes_anterior"] > 0


def test_v5_fix_no_altera_meses_con_datos(cells, world, tmp_path):
    off = _kpi_merge(_v5_namespace(cells, False), "2026-10-02", tmp_path)
    on = _kpi_merge(_v5_namespace(cells, True), "2026-10-02", tmp_path)
    antes = slice("2024-01-01", "2026-10-31")
    cols = ["lag_mau_mes_anterior", "ma_3m_mes_anterior"]
    pd.testing.assert_frame_equal(off.loc[antes, cols], on.loc[antes, cols])
