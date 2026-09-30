"""Stubs de Colab / Drive / BigQuery / CMF para ejecutar Script_Diario sin credenciales.

install(now_cl) registra módulos falsos en sys.modules y devuelve un objeto `World` con:
  - world.writes : todo lo que el notebook intentó publicar en BigQuery (tabla, df, modo, vía)
  - world.reads  : cada query recibida y qué dataset sintético se devolvió
  - world.unmatched : queries sin dataset (el dry-run falla fuerte: nada se inventa en silencio)
"""
from __future__ import annotations

import re
import sys
import types
from dataclasses import dataclass, field

import pandas as pd

from . import synth

DRIVE_ROOT = "/content/drive/.shortcut-targets-by-id/10Ha9KHrUn7dPQ7dGoiEovdVoRhmr5MSZ"


@dataclass
class World:
    now_cl: pd.Timestamp
    writes: list = field(default_factory=list)
    reads: list = field(default_factory=list)
    unmatched: list = field(default_factory=list)
    bq_month_in_monitor: int | None = None
    baseline: dict = field(default_factory=dict)   # nombre corto de tabla -> DataFrame vigente en 'BQ'

    @property
    def today(self) -> pd.Timestamp:
        return self.now_cl.tz_localize(None).normalize()

    # ---------------------------------------------------------------- dispatch
    def answer(self, sql: str) -> pd.DataFrame:
        s = sql
        t = self.today

        def hit(name, df):
            self.reads.append((name, len(df), s[:90].replace("\n", " ")))
            return df

        def dates_in(pattern):
            return re.findall(pattern, s)

        m_all = re.match(r"\s*SELECT \* FROM `([\w.-]+)`\s*$", s)
        if m_all:
            short = m_all.group(1).split(".")[-1]
            if short in self.baseline:
                return self.baseline[short].copy()
        if "MAX(fecha_ejecucion)" in s:
            m = self.bq_month_in_monitor if self.bq_month_in_monitor is not None else t.month
            return hit("monitor_mes", pd.DataFrame({"mes": [m]}))
        if "saldo_total_mm" in s and "users_audience_tags" in s:
            end = pd.Timestamp(re.search(r"DECLARE end_date\s+DATE DEFAULT DATE\('([0-9-]+)'\)", s).group(1))
            return hit("captacion", synth.captacion(end, t))
        if "habitualidad_moda_mes" in s and "principals_activated_today_month" in s:
            return hit("principales_sow", synth.principales(t))
        if "principalidad_diaria" in s:
            return hit("principalidad_diaria", synth.seg_src(t))
        if "kpi_mau" in s and "tipo_periodo" in s:
            return hit("principalidad_ref", synth.principalidad_ref(t))
        if "modelos_forecasting_gpv_productos" in s:
            return hit("gpv_productos", synth.gpv_productos(t, recaudacion="gpv_recaudacion" in s, insurance="gpv_insurance" in s))
        if "modelos_forecating_trx_cca_co" in s:
            return hit("cico_co", synth.cico(t, "co"))
        if "modelos_forecating_trx_cca" in s:
            return hit("cico_ci", synth.cico(t, "ci"))
        if "rev_atm_int" in s:
            return hit("atm", synth.atm(t))
        if "modelos_forecasting_mau_app" in s:
            return hit("mau_app", synth.mau_app(t))
        if "modelos_forecasting_mau_productos_sin_tc" in s:
            return hit("mau_prod", synth.mau_productos(t, tc=False))
        if "modelos_forecasting_mau_productos_tc" in s:
            return hit("mau_prod_tc", synth.mau_productos(t, tc=True))
        if "modelos_forecasting_ob_tc" in s:
            return hit("ob_tc", synth.ob_tc(t))
        if "fecha_ob_general" in s and "users_audience_tags" in s:
            return hit("ob_tenpo", synth.ob_tenpo(t))
        if "mau_nuevos" in s and "primera" in s:
            return hit("pace", synth.pace(t))
        if "universo_rgu" in s and "rgu_acumulado" in s:
            return hit("rgu_mtd", synth.rgu_mtd(t))
        if "universo_rgu" in s:
            return hit("rgu_hist", synth.rgu_hist(t))
        if "cohorts_current_date_nuevos" in s:
            return hit("reactive", synth.reactive(t))
        if "unit_rate" in s:
            return hit("uf", synth.uf(t))
        if "le_revenue_financiero" in s:
            return hit("le_rev_fin", pd.DataFrame({"total": [2400.0]}))
        if "revenue_tc_detalle" in s and "revenue_financiero" in s:
            return hit("tc_financiero", synth.tc_financiero(t))
        if "one_page_cuenta_rem" in s:
            return hit("one_page_rem", pd.DataFrame({"fecha": pd.date_range(t - pd.Timedelta(days=30), t - pd.Timedelta(days=1)),
                                                     "valor": 1.0}))
        if "Deuda_diaria_batch" in s:
            return hit("colocaciones", synth.colocaciones(t))
        if "OPD3.OP" in s:
            return hit("entrega_tarjetas", synth.entrega_tarjetas(t))
        if "Dias_Feriados_Chile" in s:
            return hit("feriados_sql", synth.feriados_sql())
        if "mau_tc_real" in s:
            return hit("validate_mau_tc", synth.validate_mau_tc(t))
        if "insurance.stock" in s:
            return hit("seguros_stock", synth.stock(t))
        if "gpv_tc_clp" in s:
            return hit("seguros_hist", synth.hist_ins(t))
        if "mau_rows" in s:
            if "tot_trx" in s:
                return hit("seguros_main", synth.seguros(t))
            d = dates_in(r'DATE\("([0-9-]+)"\)')
            return hit("seguros_dyn", synth.seguros(t, pd.Timestamp(d[0]), pd.Timestamp(d[1])))
        if "FORMAT_DATE('%Y-%m', fecha)" in s and "forecasting_le_seguros" in s:
            return hit("seguros_fore_plot", pd.DataFrame(columns=["fecha", "mes_anio", "dia_mes", "tipo", "revenue"]))
        if "FORMAT_DATE('%Y-%m', fecha)" in s:
            idx = pd.date_range(t.replace(day=1) - pd.DateOffset(months=3), t.replace(day=1) - pd.Timedelta(days=1))
            return hit("seguros_hist_plot", pd.DataFrame({"fecha": idx, "mes_anio": idx.strftime("%Y-%m"),
                                                          "dia_mes": idx.day, "revenue": 3.0}))
        self.unmatched.append(s[:200])
        raise RuntimeError(f"[dryrun] query sin dataset sintético: {s[:160]!r}")


# ----------------------------------------------------------------------------- módulos falsos
class _Creds:  # noqa
    pass


def install(now_cl: pd.Timestamp) -> World:
    import requests

    w = World(now_cl=now_cl)

    # ---- pandas_gbq
    gbq = types.ModuleType("pandas_gbq")

    def read_gbq(sql, *a, **k):
        return w.answer(sql)

    def to_gbq(df, destination_table=None, project_id=None, if_exists="fail", *a, **k):
        w.writes.append(dict(table=destination_table, df=df.copy(), mode=if_exists, via="pandas_gbq",
                             schema=k.get("table_schema")))

    gbq.read_gbq, gbq.to_gbq = read_gbq, to_gbq
    gbq.__version__ = "0.29.0"
    sys.modules["pandas_gbq"] = gbq
    # pandas.io.gbq delega en pandas_gbq; se enruta igual
    # ---- pydata_google_auth
    pga = types.ModuleType("pydata_google_auth")
    pga.get_user_credentials = lambda *a, **k: _Creds()
    sys.modules["pydata_google_auth"] = pga

    # ---- google.colab
    g = sys.modules.get("google") or types.ModuleType("google")
    g.__path__ = getattr(g, "__path__", [])
    sys.modules["google"] = g
    colab = types.ModuleType("google.colab")
    colab.drive = types.SimpleNamespace(mount=lambda *a, **k: None)
    colab.auth = types.SimpleNamespace(authenticate_user=lambda *a, **k: None)
    colab.userdata = types.SimpleNamespace(get=lambda k: "DUMMY-SECRET")
    sys.modules["google.colab"] = colab
    g.colab = colab

    # ---- google.cloud.bigquery / exceptions
    cloud = types.ModuleType("google.cloud")
    cloud.__path__ = []
    sys.modules["google.cloud"] = cloud
    g.cloud = cloud
    exc = types.ModuleType("google.cloud.exceptions")

    class NotFound(Exception):
        pass

    exc.NotFound = NotFound
    sys.modules["google.cloud.exceptions"] = exc
    cloud.exceptions = exc
    bq = types.ModuleType("google.cloud.bigquery")

    class _Job:
        def result(self):
            return None

    class Client:
        def __init__(self, *a, **k):
            pass

        def get_table(self, name):
            short = str(name).split(".")[-1]
            if short not in w.baseline:
                raise NotFound(f"Not found: Table {name}")
            df = w.baseline[short]

            def bqtype(sr):
                if pd.api.types.is_bool_dtype(sr):
                    return "BOOLEAN"
                if pd.api.types.is_integer_dtype(sr):
                    return "INTEGER"
                if pd.api.types.is_float_dtype(sr):
                    return "FLOAT"
                if pd.api.types.is_datetime64_any_dtype(sr):
                    return "TIMESTAMP"
                return "STRING"

            return types.SimpleNamespace(schema=[types.SimpleNamespace(name=c, field_type=bqtype(df[c])) for c in df.columns],
                                         num_rows=len(df))

        def get_dataset(self, ref):
            return types.SimpleNamespace(location="southamerica-west1")

        def create_dataset(self, *a, **k):
            return None

        def query(self, sql, *a, **k):
            w.writes.append(dict(table="<DML>", df=pd.DataFrame({"sql": [sql.strip()[:200]]}), mode="query", via="client.query", schema=None))
            return _Job()

        def load_table_from_dataframe(self, df, table_id, job_config=None, **k):
            w.writes.append(dict(table=table_id, df=df.copy(), mode=str(getattr(job_config, "write_disposition", "")),
                                 via="load_job", schema=None))
            return _Job()

    class LoadJobConfig:
        def __init__(self, **k):
            self.__dict__.update(k)

    bq.Client, bq.LoadJobConfig = Client, LoadJobConfig
    bq.WriteDisposition = types.SimpleNamespace(WRITE_TRUNCATE="WRITE_TRUNCATE", WRITE_APPEND="WRITE_APPEND")
    bq.SourceFormat = types.SimpleNamespace(PARQUET="PARQUET")
    bq.Dataset = lambda ref: types.SimpleNamespace(location=None, ref=ref)
    sys.modules["google.cloud.bigquery"] = bq
    cloud.bigquery = bq

    # ---- CMF (requests.get)
    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            rows = []
            for f, h in [("2025-01-15", "2025-02-14"), ("2025-02-15", "2025-03-14")]:
                for sub, v in [("Inferiores o iguales al equivalente de 50 unidades de fomento", "40.1"),
                               ("Inferiores o iguales al equivalente de 200 unidades de fomento y superiores al equivalente de 50 unidades de fomento", "30.2"),
                               ("Inferiores o iguales al equivalente de 5.000 unidades de fomento y superiores al equivalente de 200 unidades de fomento", "27.1")]:
                    rows.append(dict(Titulo="t", SubTitulo=sub, Valor=v, Fecha=f, Hasta=h, Tipo="35"))
            return {"TMCs": rows}

    w.cmf_calls = []

    def fake_get(url, *a, **k):
        w.cmf_calls.append(url)
        return _Resp()

    requests.get = fake_get
    return w


def make_drive_files(today: pd.Timestamp, fresh_models: bool = True):
    import os
    import shutil

    base = f"{DRIVE_ROOT}/Planificación Financiera"
    os.makedirs(f"{base}/Cierres/Metas", exist_ok=True)
    os.makedirs(f"{base}/Cierres/Proyecciones", exist_ok=True)
    models = f"{base}/KPItos Data/modelos"
    if fresh_models and os.path.isdir(models):
        shutil.rmtree(models)
    os.makedirs(models, exist_ok=True)
    os.makedirs("/shortcut-targets-by-id/10Ha9KHrUn7dPQ7dGoiEovdVoRhmr5MSZ/Planificación Financiera/KPItos Data/modelos", exist_ok=True)
    with pd.ExcelWriter(f"{base}/Cierres/Metas/Metas KPI (Consolidado).xlsx") as xw:
        synth.metas_xlsx(today).to_excel(xw, sheet_name="Consolidado", index=False)
    synth.feriados_xlsx().to_excel(f"{base}/Cierres/Proyecciones/feriados.xlsx", index=False)
    synth.feriados_xlsx()[["fecha"]].to_excel(f"{base}/Cierres/Proyecciones/feriados_gringos.xlsx", index=False)
    return models
