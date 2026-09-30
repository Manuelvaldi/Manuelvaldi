"""Datos sintéticos que imitan la FORMA (columnas/tipos/calendario) de las tablas de BigQuery
que lee Script_Diario. No pretenden reproducir los niveles reales: sirven para ejecutar el
pipeline de punta a punta (dry-run) y comparar versiones del código entre sí.

Todas las funciones son deterministas (semilla fija).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _rng(name: str) -> np.random.Generator:
    return np.random.default_rng(abs(hash(name)) % (2**32) if False else sum(map(ord, name)) * 7919)


def daily(start, end, level, name, dow_amp=0.15, dom_spikes=None, trend=0.0008, noise=0.06, weekend_drop=0.25):
    """Serie diaria positiva con tendencia, efecto día de semana, picos por día del mes y ruido."""
    idx = pd.date_range(start, end, freq="D")
    r = _rng(name)
    t = np.arange(len(idx))
    dow = idx.dayofweek.values
    base = level * (1 + trend) ** t
    wk = np.where(dow >= 5, 1 - weekend_drop, 1 + dow_amp * (dow == 4))
    v = base * wk * (1 + noise * r.standard_normal(len(idx)))
    for d, m in (dom_spikes or {}).items():
        v = np.where(idx.day == d, v * m, v)
    return pd.Series(np.maximum(v, 0.0), index=idx)


def _frame(s: pd.Series, value_col: str, extra: dict | None = None, real_until=None):
    df = pd.DataFrame({"fecha": s.index, value_col: s.values})
    df["dia_semana"] = [DOW[d] for d in df["fecha"].dt.dayofweek]
    df["dia"] = df["fecha"].dt.day
    df["mes"] = df["fecha"].dt.month
    df["year"] = df["fecha"].dt.year
    df["real"] = 1
    for k, v in (extra or {}).items():
        df[k] = v
    return df


def gpv_productos(today: pd.Timestamp, recaudacion: bool = False, insurance: bool = True) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    lines = {
        "credit_card_physical": 0.9e9, "credit_card_virtual": 2.0e9, "credit_card_crossborder": 0.15e9,
        "mastercard_physical": 1.4e9, "mastercard": 1.8e9, "crossborder": 0.1e9,
        "utility_payments": 0.35e9, "paypal": 0.0, "paypal_abonos": 0.0, "cash_in_savings": 0.5e9,
        "investment_tyba": 0.05e9, "p2p": 0.9e9, "top_ups": 0.4e9, "insurance": 0.25e9,
        "insurance_credito": 0.2e9, "insurance_no_credito": 0.05e9, "recaudacion": 3.0e9,
    }
    out = []
    for ln, lvl in lines.items():
        if (ln == "recaudacion" and not recaudacion) or (ln.startswith("insurance") and not insurance):
            continue
        if ln == "credit_card_crossborder" and not recaudacion:
            continue
        s = daily("2023-01-01", end, lvl if lvl > 0 else 1e3, "gpv" + ln, dom_spikes={1: 1.6, 5: 1.3, 20: 1.4, 30: 1.2})
        if ln.startswith("insurance"):
            s = s.where(s.index.day <= 24, 0.0)
        out.append(_frame(s, "gpv", {"linea": ln}))
    return pd.concat(out, ignore_index=True)


def cico(today: pd.Timestamp, tipo: str) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    col_seg = "cico_banco_tienda_origen" if tipo == "ci" else "cico_banco_tienda_destino"
    out = []
    for seg, lvl in [("BANCO ESTADO", 60000), ("OTROS BANCOS", 90000)]:
        trx = daily("2023-01-01", end, lvl, tipo + seg, dom_spikes={1: 1.3, 30: 1.2})
        gpv = trx * 25000
        df = _frame(trx.round(), f"trx_{tipo}", {col_seg: seg})
        df[f"gpv_{tipo}"] = gpv.values
        out.append(df)
    return pd.concat(out, ignore_index=True)


def atm(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    i = daily("2024-01-01", end, 250000, "atm_int", noise=0.3).round()
    n = daily("2024-01-01", end, 300000, "atm_nac", noise=0.3).round()
    return pd.DataFrame({"fecha": i.index, "rev_atm_int": i.values, "rev_atm_nac": n.values}).sort_values("fecha", ascending=False)


def mau_app(today: pd.Timestamp) -> pd.DataFrame:
    """MAU 'nuevo del mes' por día (pico el día 1, decae) partido en 4 tipos."""
    end = today - pd.Timedelta(days=1)
    idx = pd.date_range("2023-01-01", end, freq="D")
    r = _rng("mau")
    shape = np.array([0.30, 0.09, 0.05, 0.04, 0.035] + [0.022] * 10 + [0.018] * 10 + [0.012] * 6)
    shape = shape / shape.sum()
    rows = []
    shares = {"concurrent_user": 0.80, "resurrected_user": 0.06, "late_active_user": 0.05, "active_user_m0": 0.09}
    for d in idx:
        tot = 930000 * (1 + 0.004) ** ((d.year - 2023) * 12 + d.month) / 1.0
        tot = 700000 + 2200 * ((d.year - 2023) * 12 + d.month)
        v = tot * shape[min(d.day - 1, len(shape) - 1)] * (1 + 0.08 * r.standard_normal())
        for tp, sh in shares.items():
            rows.append((d, tp, max(v * sh, 1.0)))
    df = pd.DataFrame(rows, columns=["fecha", "tipo_mau_mes_2", "mau"])
    df["dia_semana"] = [DOW[d] for d in df["fecha"].dt.dayofweek]
    df["dia"], df["mes"], df["year"], df["real"] = df["fecha"].dt.day, df["fecha"].dt.month, df["fecha"].dt.year, 1
    df["mau"] = df["mau"].round()
    return df


def mau_productos(today: pd.Timestamp, tc: bool) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    lines = (["credit_card_physical", "credit_card_virtual", "credit_card_tarjeta_unico", "credit_card_unico"]
             if tc else ["mastercard_physical", "mastercard", "mastercard_unico", "p2p_unico", "insurance",
                          "crossborder", "paypal", "paypal_abonos", "top_ups", "utility_payments"])
    out = []
    for ln in lines:
        s = daily("2023-01-01", end, 20000, "mau" + ln, dom_spikes={1: 3.0, 5: 1.5, 20: 1.6}).round()
        out.append(_frame(s, "mau", {"linea": ln}))
    return pd.concat(out, ignore_index=True)


def ob_tc(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    out = []
    for seg, lvl in [("Large", 120), ("Medium", 90), ("Small", 70), ("XS", 400)]:
        s = daily("2023-01-01", end, lvl, "ob" + seg).round()
        out.append(_frame(s, "ob", {"segmento": seg}))
    return pd.concat(out, ignore_index=True)


def ob_tenpo(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    s = daily("2023-01-01", end, 2000, "obtenpo").round()
    return _frame(s, "mau").sort_values("fecha", ascending=False)


def rgu_hist(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    s = daily("2023-01-01", end, 2500, "rgu", dom_spikes={1: 4.0}).round()
    return _frame(s, "rgu").sort_values("fecha", ascending=False)


def rgu_mtd(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    if end.month != today.month:
        return pd.DataFrame({"fecha": [], "rgu_acumulado": []})
    s = daily(today.replace(day=1), end, 2500, "rgumtd", dom_spikes={1: 4.0}).round().cumsum()
    return pd.DataFrame({"fecha": [s.index[-1]], "rgu_acumulado": [s.iloc[-1]]})


def pace(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    a = mau_app(today).groupby("fecha")["mau"].sum()
    g = gpv_productos(today)
    g = g[~g["linea"].isin(["paypal", "paypal_abonos"])].groupby("fecha")["gpv"].sum() / 1e6
    df = pd.DataFrame({"fecha": a.index, "mau_nuevos": a.values}).merge(
        pd.DataFrame({"fecha": g.index, "gpv_mm": g.values}), on="fecha", how="outer")
    return df[df["fecha"] >= today - pd.DateOffset(months=3)].sort_values("fecha")


def reactive(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    idx = pd.date_range("2023-01-01", end, freq="D")
    cats = ["D- M1", "E- M2", "F- M3", "O- M12+"]
    prev = ["A- Inactive", "D- M1", "P- N/A"]
    r = _rng("react")
    rows = []
    for d in idx:
        for c in cats:
            for p in prev:
                rows.append((d, d.replace(day=1), c, p, float(int(abs(r.normal(2000, 400))))))
    return pd.DataFrame(rows, columns=["fecha", "mes", "categoria", "mes_anterior", "mau"])


def uf(today: pd.Timestamp) -> pd.DataFrame:
    ms = pd.date_range("2025-01-31", today, freq="ME")
    return pd.DataFrame({"fecha": ms[::-1], "valor_uf": np.linspace(40991, 37800, len(ms))})


def colocaciones(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=2)
    idx = pd.date_range("2025-09-01", end, freq="D")
    v = 100000 * np.cumprod(1 + 0.001 + 0.004 * _rng("col").standard_normal(len(idx)))
    return pd.DataFrame({"fecha": idx, "dia": idx.day, "mes": idx.month, "colocaciones": v})


def captacion(sql_end: pd.Timestamp, today: pd.Timestamp) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", sql_end - pd.Timedelta(days=1), freq="D")
    last_real = today - pd.Timedelta(days=2)
    t = np.arange(len(idx))
    tot = 330000 + 60 * t + 1500 * np.sin(idx.day.values / 31 * 2 * np.pi)
    rem = tot * 0.85
    tca = 9500 + 4 * t
    mau = 160000 + 35 * t
    real = idx <= last_real
    df = pd.DataFrame({
        "fecha": idx, "saldo_mm": np.where(real, tot, 0.0), "saldo_rem_mm": np.where(real, rem, 0.0),
        "saldo_norem_mm": np.where(real, tot - rem, 0.0), "saldo_tca_mm": np.where(real, tca, 0.0),
        "total_captaciones": np.where(real, tot + tca, 0.0), "mau_rem": np.where(real, mau, 0.0)})
    return df


def principales(today: pd.Timestamp) -> pd.DataFrame:
    idx = pd.date_range("2025-05-01", today.replace(day=1) + pd.offsets.MonthEnd(0), freq="D")
    end = today - pd.Timedelta(days=1)
    r = _rng("princ")
    rows = []
    for m, g in pd.Series(idx, index=idx).groupby(idx.to_period("M")):
        cum = 0.0
        mau_cum = 0.0
        for d in g.index:
            real = d <= end
            a = max(3200 * (1 + 0.15 * r.standard_normal()), 0) if real else 0.0
            cum += a
            mau_cum += 30000 * (1 + 0.1 * r.standard_normal()) if real else 0
            rows.append((d, d.replace(day=1), a, cum if real else 0, mau_cum if real else 0, mau_cum * 0.7 if real else 0))
    return pd.DataFrame(rows, columns=["fecha", "mes", "principals_activated_today_month", "principal_stock_mtd_query",
                                       "mau_app_mtd_query", "mau_con_renta"])


def seg_src(today: pd.Timestamp) -> pd.DataFrame:
    idx = pd.date_range(today.replace(day=1) - pd.DateOffset(months=12), today - pd.Timedelta(days=1), freq="D")
    rows = []
    for d in idx:
        for h, sh in [("principal", 0.5), ("engage", 0.3), ("distract", 0.2)]:
            rows.append((d, d.replace(day=1), h, 3200 * sh))
    return pd.DataFrame(rows, columns=["fecha", "mes", "habitualidad_anterior", "principals_activated_today_month"])


def principalidad_ref(today: pd.Timestamp) -> pd.DataFrame:
    m = today.replace(day=1)
    return pd.DataFrame({"tipo_periodo": ["MTD"] * 3, "fecha": [m] * 3,
                         "habitualidad": ["1- Principal", "2- Engage", "3- Otros"],
                         "tipo_reporte": ["App"] * 3, "kpi": ["MAU"] * 3, "valor": [420000.0, 260000.0, 170000.0]})


def seguros(today: pd.Timestamp, ref_start=None, ref_end=None, only_fore_month=False) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    rows = []
    for ident, lvl, m in [("mau_NO_TC", 900, 1), ("mau_TC", 0, 0), ("revenue_NO_TC", 0.12, 1), ("revenue_TC", 0, 0),
                          ("gpv_NO_TC", 0.5, 1), ("gpv_TC", 0, 0), ("trx", 2500, 1)]:
        if "TC" in ident and "NO_TC" not in ident:
            s = daily("2025-06-01", end, 1, "seg" + ident, noise=0.0)
            base = {"mau_TC": 4000.0, "revenue_TC": 3.2, "gpv_TC": 8.0}[ident]
            s = pd.Series(np.where(s.index.day == 5, base * 0.126, np.where(s.index.day == 20, base * 0.874, 0.0)), index=s.index)
            s = s[s > 0]
        else:
            s = daily("2025-06-01", end, lvl, "seg" + ident)
            if ident == "trx":
                s = s.round()
        if ref_start is not None:
            s = s[(s.index >= ref_start) & (s.index <= ref_end)]
        rows += [(d, ident, float(v)) for d, v in s.items()]
    return pd.DataFrame(rows, columns=["fecha", "identificador", "valor"])


def stock(today: pd.Timestamp) -> pd.DataFrame:
    end = today
    rows = []
    for cat in ["TC", "NO_TC"]:
        for pm in ["tarjeta", "otro"]:
            s = daily("2025-06-01", end, 100000, "stk" + cat + pm, trend=0.0003, noise=0.01)
            rows += [(d, cat, pm, float(v)) for d, v in s.items()]
    return pd.DataFrame(rows, columns=["fecha", "category_type", "payment_method_recod", "stock_total"])


def validate_mau_tc(today: pd.Timestamp) -> pd.DataFrame:
    return pd.DataFrame({"fecha": [today.replace(day=1)], "mau_tc_real": [4000.0]})


def hist_ins(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    s = daily("2023-01-01", end, 2.5e8, "insh")
    return pd.DataFrame({"fecha": s.index, "gpv_tc_clp": s.values * 0.9, "gpv_notc_clp": s.values * 0.1})


def entrega_tarjetas(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    s = daily(end - pd.Timedelta(days=370), end, 450, "tarj").round()
    return pd.DataFrame({"fecha": s.index, "cantidad_tarjetas": s.values})


def feriados_sql() -> pd.DataFrame:
    return pd.DataFrame({"fecha": pd.to_datetime(["2025-12-25", "2026-01-01", "2026-09-18", "2026-09-19", "2026-10-12"])})


def feriados_xlsx() -> pd.DataFrame:
    f = pd.to_datetime(["2023-01-01", "2024-01-01", "2025-01-01", "2025-12-25", "2026-01-01", "2026-04-03",
                        "2026-05-01", "2026-09-18", "2026-09-19", "2026-10-12", "2026-12-25"])
    return pd.DataFrame({"fecha": f, "feriado": 1, "irrenunciable": [1, 1, 1, 1, 1, 0, 1, 1, 0, 0, 1]})


def metas_xlsx(today: pd.Timestamp) -> pd.DataFrame:
    kpis = ["gpv_tc_vir", "gpv_tc_fis", "gpv_app", "mau_app", "rgu", "mau_concurrent", "mau_m0", "mau_resurrected",
            "mau_late_active", "mau_prp_vir", "mau_prp_fis", "mau_prp", "gpv_prp_vir", "gpv_prp_fis", "mau_tc_vir",
            "mau_tc_fis", "mau_tc", "mau_insurance", "gpv_insurance", "mau_pdc", "gpv_pdc", "mau_crossborder",
            "gpv_crossborder", "mau_paypal", "gpv_paypal", "mau_paypal_abonos", "gpv_paypal_abonos", "mau_top_ups",
            "gpv_top_ups", "mau_p2p", "gpv_p2p", "ob_tc_large", "ob_tc_medium", "ob_tc_small", "ob_tc_xs"]
    cols = [pd.Timestamp(2026, m, 1) for m in range(1, 13)]
    df = pd.DataFrame({"KPI": kpis})
    for c in cols:
        df[c] = 1_000_000.0
    return df


def tc_financiero(today: pd.Timestamp) -> pd.DataFrame:
    end = today - pd.Timedelta(days=1)
    if end.month != today.month and today.day == 1:
        end = today - pd.Timedelta(days=1)
    idx = pd.date_range(end.replace(day=1), end, freq="D")
    v = pd.Series(1e7, index=idx)
    return pd.DataFrame({"fecha": idx, "revenue_tc_financiero": v.values, "revenue_acumulado": v.cumsum().values})
