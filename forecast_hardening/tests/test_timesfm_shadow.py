import numpy as np
import pandas as pd
import pytest

from forecast_hardening import timesfm_shadow as tsh
from forecast_hardening.dryrun import synth


class StubTimesFM:
    """Imita la interfaz de TimesFM 2.5 (forecast / forecast_with_covariates) con seasonal-naive."""
    calls = 0

    def forecast(self, horizon, inputs):
        StubTimesFM.calls += 1
        pts = []
        for x in inputs:
            x = np.asarray(x, dtype=float)
            pts.append(np.array([x[-7 + (i % 7)] for i in range(horizon)]))
        return np.stack(pts), np.zeros((len(inputs), horizon, 10))

    def forecast_with_covariates(self, inputs, dynamic_numerical_covariates, dynamic_categorical_covariates, **kw):
        n = len(dynamic_numerical_covariates["is_day1"][0]) - len(inputs[0])
        assert n > 0 and len(dynamic_categorical_covariates["dow"][0]) == len(inputs[0]) + n
        return [self.forecast(n, inputs)[0][0]], [None]


@pytest.fixture(scope="module")
def serie():
    t = pd.Timestamp("2026-09-30")
    s = synth.daily("2024-01-01", t, 10000, "tsh", dom_spikes={1: 4.0, 5: 1.5, 20: 1.6})
    return s


def test_backtest_sin_fuga_y_metricas(serie):
    months = tsh.last_closed_months(serie, 3)
    assert [str(m) for m in months] == ["2026-07", "2026-08", "2026-09"]
    fc = {"snaive": tsh.SeasonalNaive(), "domprof": tsh.DomProfile(), "tfm": tsh.TimesFMForecaster(model=StubTimesFM()),
          "tfm_xreg": tsh.TimesFMForecaster(model=StubTimesFM(), use_xreg=True), "xgb": tsh.XGBCalendar()}
    bt = tsh.run_backtest(serie, fc, months, cutoffs=(2, 14))
    assert bt["error"].isna().all() if "error" in bt else True
    assert set(bt["model"]) == set(fc) and len(bt) == 3 * 2 * len(fc)
    assert (bt["ape_cierre"] >= 0).all()
    # sanidad: en una serie limpia con tendencia suave todos aterrizan cerca del real al corte 14
    s = tsh.summarize(bt).reset_index()
    assert (s[s.cutoff == 14]["ape_cierre_mediana"] < 0.10).all()
    assert np.isfinite(bt["mape_diario"]).all()


def test_el_forecaster_solo_ve_datos_hasta_el_corte(serie):
    vistos = []

    def espia(hist, future):
        vistos.append((hist.index.max(), future[0]))
        return np.ones(len(future))

    tsh.run_backtest(serie, {"e": espia}, [pd.Period("2026-08")], cutoffs=(7,))
    assert vistos == [(pd.Timestamp("2026-08-07"), pd.Timestamp("2026-08-08"))]


def test_compare_exige_margen_y_muestra_minima():
    rows = []
    for m in range(12):
        for c in (2, 7):
            rows += [dict(month=f"m{m}", cutoff=c, model="actual", ape_cierre=0.04, sesgo_cierre=0.0, mape_diario=0.1),
                     dict(month=f"m{m}", cutoff=c, model="tfm", ape_cierre=0.03, sesgo_cierre=0.0, mape_diario=0.09)]
    bt = pd.DataFrame(rows)
    assert tsh.compare(bt, "actual", "tfm")["decision"] == "CANDIDATO_A_REEMPLAZAR"
    assert tsh.compare(bt[bt.month.isin(["m0", "m1"])], "actual", "tfm")["decision"] == "NO_CONCLUYENTE"
    bt.loc[bt.model == "tfm", "ape_cierre"] = 0.039       # mejora <10%
    assert tsh.compare(bt, "actual", "tfm")["decision"] == "MANTENER_ACTUAL"


def test_timesfm_sin_paquete_falla_al_usarse_no_al_importar(serie):
    f = tsh.TimesFMForecaster()        # construir no importa timesfm
    try:
        import timesfm  # noqa
        pytest.skip("timesfm instalado")
    except ImportError:
        with pytest.raises(ImportError):
            f(serie, pd.date_range("2026-10-01", periods=3))


def test_un_forecaster_que_falla_no_tumba_el_backtest(serie):
    def malo(h, f):
        raise ValueError("boom")
    bt = tsh.run_backtest(serie, {"malo": malo, "ok": tsh.SeasonalNaive()}, [pd.Period("2026-09")], cutoffs=(7,))
    assert "ValueError" in bt[bt.model == "malo"]["error"].iloc[0]
    assert bt[bt.model == "ok"]["ape_cierre"].notna().all()


def test_mape_forma_ignora_el_nivel_y_mide_el_reparto():
    assert tsh._mape_forma(np.array([1., 2., 3.]), np.array([10., 20., 30.])) == pytest.approx(0.0)   # mismo reparto, otro nivel
    assert tsh._mape_forma(np.array([3., 2., 1.]), np.array([10., 20., 30.])) > 0.3
    rows = [dict(month=f"m{m}", cutoff=c, model=n, ape_cierre=0.03, sesgo_cierre=0., mape_diario=0.1, mape_forma=f)
            for m in range(12) for c in (2, 7) for n, f in (("a", 0.10), ("b", 0.06))]
    assert tsh.compare(pd.DataFrame(rows), "a", "b", metric="mape_forma")["decision"] == "CANDIDATO_A_REEMPLAZAR"
