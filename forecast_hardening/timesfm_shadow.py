"""Backtest "en la sombra" de TimesFM (y baselines) contra el método actual de Script_Diario.

NO toca producción: solo mide. Un solo archivo para subirlo a Drive y hacer
`sys.path.append(directorio_salida); import timesfm_shadow as tsh`.

Qué responde: ¿un forecaster alternativo predice mejor el CIERRE DE MES (y la forma diaria) que el
actual, con la misma información disponible al corte, en los mismos meses/cortes?

    tsh.run_backtest(series, {"actual": mi_callable, "timesfm": tsh.TimesFMForecaster(...)},
                     months=tsh.last_closed_months(series, 6), cutoffs=(2, 7, 14, 21))

Contrato de un forecaster: callable(history: pd.Series, future: pd.DatetimeIndex) -> np.ndarray
  * history: serie diaria observada (índice fecha) SOLO hasta el corte (sin fuga de datos).
  * future : fechas a proyectar (resto del mes).
Licencia: usar TimesFM 2.5 (Apache-2.0). Los pesos de TimesFM 3.0 son no comerciales.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Sequence

import numpy as np
import pandas as pd

Forecaster = Callable[[pd.Series, pd.DatetimeIndex], np.ndarray]

BILLING_DAYS = (5, 20)


# ------------------------------------------------------------------------------------ calendario
def calendar_frame(idx: pd.DatetimeIndex, holidays: Iterable = ()) -> pd.DataFrame:
    idx = pd.DatetimeIndex(idx)
    hol = set(pd.to_datetime(list(holidays)).normalize())
    return pd.DataFrame({
        "dow": idx.dayofweek, "dom": idx.day, "month": idx.month,
        "is_day1": (idx.day == 1).astype(int), "is_eom": idx.is_month_end.astype(int),
        "is_bill5": (idx.day == 5).astype(int), "is_bill20": (idx.day == 20).astype(int),
        "is_holiday": [int(d.normalize() in hol) for d in idx],
        "dom_sin": np.sin(2 * np.pi * idx.day / 31.0), "dom_cos": np.cos(2 * np.pi * idx.day / 31.0),
    }, index=idx)


def clean_daily(s: pd.Series) -> pd.Series:
    """Serie diaria continua (días faltantes -> NaN), float, índice normalizado."""
    s = s.copy()
    s.index = pd.DatetimeIndex(pd.to_datetime(s.index)).normalize()
    s = s.groupby(level=0).sum(min_count=1).astype(float).sort_index()
    return s.reindex(pd.date_range(s.index.min(), s.index.max(), freq="D"))


# ------------------------------------------------------------------------------------ baselines
@dataclass
class SeasonalNaive:
    """Promedio/mediana del mismo día de la semana en las últimas k semanas."""
    k: int = 4
    agg: str = "median"

    def __call__(self, history, future):
        h = clean_daily(history).dropna()
        out = []
        for d in future:
            same = h[(h.index.dayofweek == d.dayofweek) & (h.index < d)].tail(self.k)
            out.append(float(getattr(same, self.agg)()) if len(same) else float(h.tail(28).mean()))
        return np.array(out)


@dataclass
class DomProfile:
    """Perfil por día del mes de los últimos `months` meses cerrados × total mensual esperado.

    Es el equivalente simple de la lógica 'pace' del pipeline (curva MTD/cierre)."""
    months: int = 3
    growth: float = 1.0

    def __call__(self, history, future):
        h = clean_daily(history)
        first_future = future[0]
        closed = h[h.index < first_future.replace(day=1)]
        per = closed.groupby(closed.index.to_period("M"))
        tot = per.sum(min_count=1).dropna()
        tot = tot[per.size().reindex(tot.index) >= per.apply(lambda x: x.index[0].days_in_month).reindex(tot.index)].tail(self.months)
        if tot.empty:
            return SeasonalNaive()(history, future)
        prof = {}
        for p in tot.index:
            m = closed[closed.index.to_period("M") == p]
            for d, v in m.items():
                prof.setdefault(d.day, []).append(v / tot[p])
        share = {d: float(np.mean(v)) for d, v in prof.items()}
        month_total = float(tot.mean()) * self.growth
        return np.array([month_total * share.get(d.day, np.mean(list(share.values()))) for d in future])


@dataclass
class XGBCalendar:
    """Árbol de gradiente con calendario + nivel reciente (aprox. del método actual, sin recursión)."""
    holidays: Sequence = ()
    train_days: int = 540
    params: dict = field(default_factory=lambda: dict(n_estimators=250, learning_rate=0.05, max_depth=4,
                                                      subsample=0.85, colsample_bytree=0.85, random_state=7))

    def __call__(self, history, future):
        from xgboost import XGBRegressor
        h = clean_daily(history).dropna().tail(self.train_days)
        X = calendar_frame(h.index, self.holidays)
        lvl = h.rolling(28, min_periods=7).mean().shift(1)
        X["lvl"] = lvl.values
        X = X.iloc[7:]
        y = np.log1p(h.clip(lower=0)).iloc[7:]
        m = XGBRegressor(**self.params).fit(X.fillna(0.0), y)
        Xf = calendar_frame(future, self.holidays)
        Xf["lvl"] = float(h.tail(28).mean())
        return np.maximum(np.expm1(m.predict(Xf)), 0.0)


@dataclass
class Blend:
    """Promedio ponderado de otros forecasters (p. ej. actual + timesfm)."""
    parts: Sequence[Forecaster]
    weights: Sequence[float] | None = None

    def __call__(self, history, future):
        w = np.array(self.weights if self.weights is not None else [1.0] * len(self.parts), dtype=float)
        preds = np.stack([p(history, future) for p in self.parts])
        return (preds * (w / w.sum())[:, None]).sum(axis=0)


# ------------------------------------------------------------------------------------ TimesFM
class TimesFMForecaster:
    """Adaptador de TimesFM 2.5 (PyTorch). Carga perezosa: sin el paquete, falla al usarse, no al importar.

        pip install "timesfm[torch]"     # y, para covariables (XReg): pip install "timesfm[xreg]"
        f = TimesFMForecaster(use_xreg=True, holidays=feriados)

    `model` permite inyectar un objeto con la misma interfaz (`forecast`, `forecast_with_covariates`),
    usado por las pruebas y por si ya tienen el modelo cargado en memoria.
    """

    def __init__(self, model=None, max_context: int = 1024, max_horizon: int = 64, use_xreg: bool = False,
                 holidays: Sequence = (), repo_id: str = "google/timesfm-2.5-200m-pytorch",
                 xreg_mode: str = "xreg + timesfm", ridge: float = 1.0):
        self.model, self.max_context, self.max_horizon = model, max_context, max_horizon
        self.use_xreg, self.holidays, self.repo_id = use_xreg, holidays, repo_id
        self.xreg_mode, self.ridge = xreg_mode, ridge

    def _ensure(self):
        if self.model is not None:
            return
        import timesfm  # noqa: WPS433
        m = timesfm.TimesFM_2p5_200M_torch.from_pretrained(self.repo_id)
        m.compile(timesfm.ForecastConfig(
            max_context=self.max_context, max_horizon=self.max_horizon, normalize_inputs=True,
            use_continuous_quantile_head=True, force_flip_invariance=True, infer_is_positive=True,
            fix_quantile_crossing=True, return_backcast=self.use_xreg))
        self.model = m

    def __call__(self, history, future):
        self._ensure()
        h = clean_daily(history)
        ctx = h.interpolate(limit_area="inside").ffill().bfill().to_numpy(dtype=float)[-self.max_context:]
        hz = len(future)
        if not self.use_xreg:
            point, _ = self.model.forecast(horizon=hz, inputs=[ctx])
            return np.maximum(np.asarray(point)[0][:hz], 0.0)
        idx_ctx = h.index[-len(ctx):]
        full = idx_ctx.append(pd.DatetimeIndex(future))
        cal = calendar_frame(full, self.holidays)
        num = {c: [cal[c].to_numpy(dtype=float)] for c in ("is_day1", "is_eom", "is_bill5", "is_bill20", "is_holiday", "dom_sin", "dom_cos")}
        cat = {"dow": [cal["dow"].astype(int).tolist()]}
        out, _ = self.model.forecast_with_covariates(
            inputs=[ctx.tolist()], dynamic_numerical_covariates=num, dynamic_categorical_covariates=cat,
            xreg_mode=self.xreg_mode, ridge=self.ridge, normalize_xreg_target_per_input=True)
        return np.maximum(np.asarray(out[0])[:hz], 0.0)


# ------------------------------------------------------------------------------------ backtest
def last_closed_months(series: pd.Series, n: int = 6) -> list[pd.Period]:
    s = clean_daily(series).dropna()
    last = s.index.max()
    cur = last.to_period("M")
    full_last = last == last + pd.offsets.MonthEnd(0)
    months = pd.period_range(end=cur if full_last else cur - 1, periods=n, freq="M")
    return list(months)


def run_backtest(series: pd.Series, forecasters: Dict[str, Forecaster], months: Sequence[pd.Period],
                 cutoffs: Sequence[int] = (2, 7, 14, 21), min_history_days: int = 120,
                 scale: float = 1.0) -> pd.DataFrame:
    """Para cada (mes, corte, modelo): con datos hasta el día `corte` predice el resto del mes.

    landing = MTD real (hasta el corte) + suma del pronóstico del resto. Métricas:
      ape_cierre  |landing - real_mes| / real_mes
      sesgo_cierre (landing - real_mes) / real_mes
      mape_diario  MAPE de los días proyectados
    `scale` solo para legibilidad de los totales (p. ej. 1e6).
    """
    s = clean_daily(series)
    rows = []
    for p in months:
        start, end = p.start_time.normalize(), p.end_time.normalize()
        month = s.reindex(pd.date_range(start, end, freq="D"))
        if month.isna().any():
            continue                      # solo meses completos
        real_total = float(month.sum())
        for c in cutoffs:
            cut = start + pd.Timedelta(days=c - 1)
            if cut >= end:
                continue
            hist = s[s.index <= cut]
            if hist.dropna().shape[0] < min_history_days:
                continue
            future = pd.date_range(cut + pd.Timedelta(days=1), end, freq="D")
            mtd = float(month[:cut].sum())
            actual_rest = month[future].to_numpy()
            for name, f in forecasters.items():
                try:
                    pred = np.asarray(f(hist, future), dtype=float)
                    assert pred.shape == (len(future),) and np.isfinite(pred).all()
                except Exception as e:
                    rows.append(dict(month=str(p), cutoff=c, model=name, error=f"{type(e).__name__}: {str(e)[:80]}"))
                    continue
                landing = mtd + float(pred.sum())
                nz = actual_rest > 0
                rows.append(dict(month=str(p), cutoff=c, model=name, real_total=real_total / scale,
                                 landing=landing / scale, ape_cierre=abs(landing - real_total) / real_total,
                                 sesgo_cierre=(landing - real_total) / real_total,
                                 mape_diario=float(np.mean(np.abs(pred[nz] - actual_rest[nz]) / actual_rest[nz])) if nz.any() else np.nan))
    return pd.DataFrame(rows)


def summarize(bt: pd.DataFrame) -> pd.DataFrame:
    ok = bt.dropna(subset=["ape_cierre"]) if "ape_cierre" in bt else bt
    g = ok.groupby(["model", "cutoff"]).agg(ape_cierre_mediana=("ape_cierre", "median"), ape_cierre_media=("ape_cierre", "mean"),
                                            sesgo_medio=("sesgo_cierre", "mean"), mape_diario_mediana=("mape_diario", "median"),
                                            n=("ape_cierre", "size"))
    return g.round(4)


def compare(bt: pd.DataFrame, current: str, challenger: str) -> dict:
    """Decisión por evidencia: el desafiante solo 'gana' si supera al actual con margen y de forma consistente."""
    ok = bt.dropna(subset=["ape_cierre"])
    a = ok[ok.model == current].set_index(["month", "cutoff"])["ape_cierre"]
    b = ok[ok.model == challenger].set_index(["month", "cutoff"])["ape_cierre"]
    j = pd.concat([a, b], axis=1, keys=["cur", "cha"]).dropna()
    if j.empty:
        return dict(n=0, decision="SIN_DATOS")
    win = float((j["cha"] < j["cur"]).mean())
    rel = float(1 - j["cha"].median() / j["cur"].median()) if j["cur"].median() > 0 else np.nan
    mape_a = ok[ok.model == current]["mape_diario"].median()
    mape_b = ok[ok.model == challenger]["mape_diario"].median()
    decision = "CANDIDATO_A_REEMPLAZAR" if (len(j) >= 12 and win >= 0.65 and rel >= 0.10) else (
        "NO_CONCLUYENTE" if len(j) < 12 else "MANTENER_ACTUAL")
    return dict(n=int(len(j)), win_rate=round(win, 3), mejora_rel_mediana_ape=round(rel, 3),
                mape_diario_actual=round(float(mape_a), 4), mape_diario_desafiante=round(float(mape_b), 4), decision=decision)
