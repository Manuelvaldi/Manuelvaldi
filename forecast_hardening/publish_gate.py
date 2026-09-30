"""Compuerta de publicación para Script_Diario (V12).

Se inserta UNA vez al inicio del notebook (la celda V12 incluye este archivo tal cual) y
'engancha' las funciones de escritura que ya usa el notebook:

    pandas_gbq.to_gbq                      (la mayoría de las celdas)
    DataFrame.to_gbq                       (vía pandas_gbq.to_gbq)
    bigquery.Client.load_table_from_dataframe   (captación)
    bigquery.Client.query con DML          (DELETE del monitoreo)

por lo tanto el código de negocio del notebook NO cambia. Modos (env PIPELINE_MODE):

    stage   (default)  acumula todo en memoria; al final `GATE.commit_all()` valida por tabla y
                       entre tablas y publica SOLO los grupos sanos, en el mismo orden original.
                       Un grupo con problemas se retiene completo: se conserva la versión anterior
                       (consistente) de todas sus tablas en vez de publicar una mezcla.
    live               escribe inmediatamente como hoy, pero con validación por tabla.
    dry_run            como stage pero no escribe nada en BigQuery; deja el reporte.

La salida (nombres de columnas y tipos) se alinea con la tabla vigente en BigQuery cuando existe,
de modo que un float "casualmente entero" no cambie una columna de FLOAT a INTEGER de un día a otro.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import OrderedDict

import numpy as np
import pandas as pd

PROJECT_DEFAULT = "tenpo-bi-prod"

# grupo -> tablas que DEBEN salir juntas (todo o nada)
GROUPS: "OrderedDict[str, list[str]]" = OrderedDict([
    ("captacion", ["forecasting_le_captacion", "captaciones_monitoreo_le", "forecasting_le_captacion_90d"]),
    ("principales", ["forecasting_le_clientes_principales"]),
    ("tesoreria", ["flujos_tesoreria", "flujos_tesoreria_ajustados"]),
    ("seguros", ["forecasting_le_seguros", "forecasting_le_seguros_stock", "forecast_le_insurance"]),
    ("tarjetas", ["entrega_tarjetas"]),
    ("kpi_core", ["forecasting_rgu", "forecasting_mau_productos", "forecasting_mau_reactive_desglosado",
                  "forecasting_categorias", "forecasting_gpv_productos", "forecasting_gpv_app",
                  "forecasting_gpv_cca_ci", "forecasting_gpv_cca_co", "porc_insurance",
                  "forecasting_ob_tc", "ob_tenpo"]),
    ("revenue_fin", ["forecasting_revenue_financiero"]),
    ("referencias", ["tmc", "one_page_cuenta_remunerada"]),
    ("colocaciones", ["colocacion_90", "le_colocacion"]),
    ("auditoria", ["pipeline_audit"]),
])
_TABLE2GROUP = {t: g for g, ts in GROUPS.items() for t in ts}

# columnas que, junto a `fecha`, identifican una fila (para detectar duplicados)
_KEY_HELPERS = ["linea", "producto", "identificador", "category_type", "payment_method_recod", "segmento",
                "categoria", "mes_anterior", "fecha_ejecucion", "status", "tipo"]

_DML = re.compile(r"^\s*(DELETE|INSERT|UPDATE|MERGE|CREATE|DROP|TRUNCATE|ALTER)\b", re.I)


class PublishError(RuntimeError):
    pass


def short_name(table: str) -> str:
    return str(table).split(".")[-1]


def fq_name(table: str, project: str = PROJECT_DEFAULT) -> str:
    parts = str(table).replace("`", "").split(".")
    return ".".join(parts) if len(parts) == 3 else f"{project}.{'.'.join(parts)}"


def _type_class_bq(t: str) -> str:
    t = str(t).upper()
    if t in ("INTEGER", "INT64"):
        return "INT"
    if t in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
        return "FLOAT"
    if t in ("BOOLEAN", "BOOL"):
        return "BOOL"
    if t in ("DATE", "DATETIME", "TIMESTAMP", "TIME"):
        return "TEMPORAL"
    return "STRING"


def _type_class_pd(s: pd.Series) -> str:
    if pd.api.types.is_bool_dtype(s):
        return "BOOL"
    if pd.api.types.is_integer_dtype(s):
        return "INT"
    if pd.api.types.is_float_dtype(s):
        return "FLOAT"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "TEMPORAL"
    return "STRING"


class _DummyJob:
    def result(self, *a, **k):
        return None


class PublishGate:
    def __init__(self, mode: str = "stage", today=None, report_dir: str | None = None,
                 allow_schema_drift: bool = False, credentials_getter=None, log=print):
        assert mode in ("stage", "live", "dry_run"), mode
        self.mode = mode
        self.today = today
        self.report_dir = report_dir
        self.allow_schema_drift = allow_schema_drift
        self.creds = credentials_getter or (lambda: None)
        self.log = log
        self.ops: list[dict] = []          # todas las operaciones, en orden
        self.results: list[dict] = []      # resultado por grupo (se llena en commit)
        self._orig = {}
        self._baseline_cache: dict = {}
        self.staged: dict = {}             # tabla corta -> (nombre completo, DataFrame) de lo último comprometido
        self.issues_live: list[dict] = []

    # ------------------------------------------------------------------ enganche
    def install(self):
        import pandas_gbq
        prev = getattr(pandas_gbq, "_v12_gate", None)
        if prev is not None and prev is not self:
            # re-ejecutar la celda helper NO debe anidar compuertas: se desinstala la anterior
            if prev.ops:
                self.log(f"[GATE] !! la compuerta anterior tenía {len(prev.ops)} operaciones en cola sin publicar (se descartan)")
            prev.uninstall()
        pandas_gbq._v12_gate = self
        self._orig["to_gbq"] = pandas_gbq.to_gbq
        pandas_gbq.to_gbq = self._to_gbq
        try:
            from google.cloud import bigquery
            self._orig["load"] = bigquery.Client.load_table_from_dataframe
            self._orig["query"] = bigquery.Client.query
            gate = self

            def _load(client, dataframe, destination, *a, **k):
                return gate._capture_load(client, dataframe, destination, a, k)

            def _query(client, sql, *a, **k):
                if isinstance(sql, str) and _DML.match(sql):
                    return gate._capture_dml(client, sql, a, k)
                return gate._orig["query"](client, sql, *a, **k)

            bigquery.Client.load_table_from_dataframe = _load
            bigquery.Client.query = _query
        except Exception as e:  # pragma: no cover
            self.log(f"[GATE] !! no se pudo enganchar bigquery.Client: {e}")
        self.log(f"[GATE] instalada | modo={self.mode} | grupos={list(GROUPS)}")
        return self

    def uninstall(self):
        import pandas_gbq
        if getattr(pandas_gbq, "_v12_gate", None) is self:
            pandas_gbq._v12_gate = None
        if "to_gbq" in self._orig:
            pandas_gbq.to_gbq = self._orig["to_gbq"]
            self._orig.pop("to_gbq")
        if "load" in self._orig:
            from google.cloud import bigquery
            bigquery.Client.load_table_from_dataframe = self._orig.pop("load")
            bigquery.Client.query = self._orig.pop("query")

    # ------------------------------------------------------------------ captura
    def _to_gbq(self, dataframe, destination_table=None, project_id=None, if_exists="fail", *a, **k):
        table = fq_name(destination_table, project_id or PROJECT_DEFAULT)
        op = dict(kind="to_gbq", table=table, dest=destination_table, df=dataframe, mode=if_exists, args=a,
                  kwargs=dict(k, project_id=project_id, if_exists=if_exists), t=time.time())
        return self._register(op)

    def _capture_load(self, client, dataframe, destination, a, k):
        table = fq_name(str(destination))
        jc = k.get("job_config")
        disp = str(getattr(jc, "write_disposition", "WRITE_EMPTY"))
        op = dict(kind="load", table=table, df=dataframe, mode="append" if "APPEND" in disp else "replace",
                  client=client, args=a, kwargs=k, t=time.time())
        self._register(op)
        return _DummyJob()

    def _capture_dml(self, client, sql, a, k):
        m = re.search(r"`([\w.-]+)`", sql)
        table = m.group(1) if m else "<dml>"
        op = dict(kind="dml", table=fq_name(table) if m else table, df=None, mode="dml", client=client,
                  sql=sql, args=a, kwargs=k, t=time.time())
        self._register(op)
        return _DummyJob()

    def _register(self, op):
        op["short"] = short_name(op["table"])
        op["group"] = _TABLE2GROUP.get(op["short"], "otros:" + op["short"])
        if self.mode == "live":
            return self._live(op)
        self.ops.append(op)
        n = "" if op["df"] is None else f" {op['df'].shape[0]}x{op['df'].shape[1]}"
        self.log(f"[GATE:{self.mode}] en cola {op['kind']} -> {op['short']}{n} (grupo {op['group']})")
        return None

    def _live(self, op):
        if op["kind"] != "dml":
            issues = self.check_table(op)
            blocks = [i for i in issues if i["level"] == "BLOCK"]
            self.issues_live += [dict(i, table=op["short"]) for i in issues]
            for i in issues:
                self.log(f"[GATE:live] {i['level']} {op['short']}: {i['msg']}")
            if blocks:
                self.log(f"[GATE:live] !! {op['short']} NO se publica (se conserva la versión anterior)")
                return None
            self._align(op)
        return self._execute(op)

    # ------------------------------------------------------------------ línea base BQ
    def baseline(self, table):
        if table in self._baseline_cache:
            return self._baseline_cache[table]
        res = None
        try:
            from google.cloud import bigquery
            client = bigquery.Client(project=table.split(".")[0], credentials=self.creds())
            t = client.get_table(table)
            res = dict(schema={f.name: _type_class_bq(f.field_type) for f in t.schema}, rows=int(t.num_rows or 0))
        except Exception as e:
            res = dict(error=f"{type(e).__name__}: {str(e)[:80]}")
        self._baseline_cache[table] = res
        return res

    # ------------------------------------------------------------------ validación por tabla
    def check_table(self, op) -> list[dict]:
        df, out = op["df"], []

        def add(level, msg):
            out.append(dict(level=level, msg=msg))

        if df is None or len(df.columns) == 0:
            return [dict(level="BLOCK", msg="sin columnas")]
        if len(df) == 0:
            add("BLOCK", "DataFrame vacío")
            return out
        num = df.select_dtypes(include=[np.number])
        if len(num.columns) and np.isinf(num.to_numpy(dtype=float, na_value=np.nan)).any():
            add("BLOCK", "hay valores infinitos")
        if df.isna().all(axis=None):
            add("BLOCK", "todo NaN")
        if "fecha" in df.columns:
            key = ["fecha"] + [c for c in _KEY_HELPERS if c in df.columns]
            d = int(df.duplicated(subset=key).sum())
            if d:
                add("BLOCK", f"{d} filas duplicadas por {key}")
        neg_cols = [c for c in num.columns
                    if re.search(r"(pred|real|saldo|gpv|mau|rgu|ob_|trx)", c) and "meta" not in c and "delta" not in c
                    and (num[c] < 0).any()]
        if neg_cols:
            add("WARN", f"valores negativos en {neg_cols[:5]}")
        # línea base
        if op["kind"] != "dml":
            b = self.baseline(op["table"])
            if "error" in b:
                add("INFO", f"sin línea base en BQ ({b['error']})")
            else:
                ex = b["schema"]
                missing = [c for c in ex if c not in df.columns]
                extra = [c for c in df.columns if c not in ex]
                if missing and not self.allow_schema_drift:
                    add("BLOCK", f"faltan columnas existentes en BQ: {missing[:6]}")
                elif missing:
                    add("WARN", f"faltan columnas existentes en BQ: {missing[:6]} (drift permitido)")
                if extra:
                    add("WARN", f"columnas nuevas vs BQ: {extra[:6]}")
                for c in df.columns:
                    if c in ex:
                        a, bcls = _type_class_pd(df[c]), ex[c]
                        if a != bcls and {a, bcls} != {"INT", "FLOAT"} and not (a == "STRING" and bcls == "TEMPORAL") \
                                and not (a == "TEMPORAL" and bcls == "STRING"):
                            lvl = "WARN" if self.allow_schema_drift else "BLOCK"
                            add(lvl, f"tipo de '{c}': {a} vs BQ {bcls}")
                if b["rows"] and op["mode"] == "replace" and len(df) < 0.5 * b["rows"]:
                    add("BLOCK", f"filas {len(df)} < 50% de las vigentes ({b['rows']})")
        return out

    def _align(self, op):
        """Alinea tipos INT/FLOAT con la tabla vigente (sin tocar valores)."""
        df = op["df"]
        if df is None:
            return
        b = self.baseline(op["table"])
        if "error" in b:
            return
        df = df.copy()
        for c in df.columns:
            cls = b["schema"].get(c)
            if cls is None:
                continue
            cur = _type_class_pd(df[c])
            if cls == "INT" and cur == "FLOAT":
                v = df[c]
                if ((v.dropna() % 1) == 0).all():
                    df[c] = v.round().astype("Int64")
            elif cls == "FLOAT" and cur == "INT":
                df[c] = df[c].astype(float)
        op["df"] = df

    # ------------------------------------------------------------------ chequeos entre tablas
    def cross_checks(self, frames: dict) -> list[dict]:
        out = []

        def add(level, msg):
            out.append(dict(level=level, msg=msg))

        def F(name):
            return frames.get(name)

        core = {n: f for n, f in frames.items() if n in GROUPS["kpi_core"] and "fecha" in f.columns}
        # C1: todas las tablas del grupo cubren el mismo mes
        months = {}
        for n, f in core.items():
            fd = pd.to_datetime(f["fecha"], errors="coerce", dayfirst=False)
            months[n] = sorted({p for p in fd.dt.to_period("M").dropna().astype(str).unique()})
        ref = months.get("forecasting_gpv_app") or next(iter(months.values()), [])
        for n, m in months.items():
            if m != ref:
                add("BLOCK", f"{n} cubre {m[:3]} pero forecasting_gpv_app cubre {ref[:3]}")
        # C2: corte real/forecast parecido entre tablas
        def last_real(f, col):
            if col not in f.columns:
                return None
            fd = pd.to_datetime(f["fecha"], errors="coerce")
            s = pd.to_numeric(f[col], errors="coerce")
            ok = fd[s.notna()]
            return ok.max() if len(ok) else pd.NaT
        cut = {"forecasting_gpv_app": "gpv", "forecasting_categorias": "mau_app"}
        cuts = {n: last_real(F(n), c) for n, c in cut.items() if F(n) is not None}
        cuts = {n: v for n, v in cuts.items() if v is not None and not pd.isna(v)}
        if len(cuts) >= 2:
            vals = list(cuts.values())
            gap = (max(vals) - min(vals)).days
            if gap > 1:
                add("WARN", f"último día real difiere {gap}d entre tablas: { {k: str(v.date()) for k, v in cuts.items()} }")
        # C3: suma de productos == GPV App en días futuros (productos en MM, app en CLP)
        gp, ga = F("forecasting_gpv_productos"), F("forecasting_gpv_app")
        if gp is not None and ga is not None and "gpv_real_pred" in ga.columns:
            prod = [c for c in gp.columns if c.startswith("gpv_real_pred_") and "cumsum" not in c]
            a = ga.assign(fecha=pd.to_datetime(ga["fecha"])).set_index("fecha")
            p = gp.assign(fecha=pd.to_datetime(gp["fecha"])).set_index("fecha")[prod].apply(pd.to_numeric, errors="coerce")
            fut = a.index[pd.to_numeric(a["gpv"], errors="coerce").isna()] if "gpv" in a.columns else a.index[:0]
            fut = fut.intersection(p.index)
            if len(fut):
                lhs = p.loc[fut].sum(axis=1)
                rhs = pd.to_numeric(a.loc[fut, "gpv_real_pred"], errors="coerce") / 1e6
                rel = ((lhs - rhs).abs() / rhs.abs().replace(0, np.nan)).max()
                if rel > 0.05:
                    add("BLOCK", f"suma de productos vs GPV App en días futuros difiere {rel:.1%}")
                elif rel > 0.005:
                    add("WARN", f"suma de productos vs GPV App en días futuros difiere {rel:.2%}")
        # C4: MAU App vs subcategorías (acumulado del mes)
        c = F("forecasting_categorias")
        if c is not None and "mau_real_pred_app" in c.columns:
            parts = [f"mau_real_pred_{k}" for k in ("concurrent", "m0", "resurrected", "late_active")]
            if all(p in c.columns for p in parts):
                tot = pd.to_numeric(c["mau_real_pred_app"], errors="coerce").sum()
                sub = sum(pd.to_numeric(c[p], errors="coerce").sum() for p in parts)
                if tot > 0:
                    rel = abs(sub - tot) / tot
                    if rel > 0.02:
                        add("BLOCK", f"MAU App {tot:,.0f} vs subcategorías {sub:,.0f} ({rel:.2%})")
                    elif rel > 0.005:
                        add("WARN", f"MAU App {tot:,.0f} vs subcategorías {sub:,.0f} ({rel:.2%})")
        # C5: desglose reactive suma al concurrent por día
        r = F("forecasting_mau_reactive_desglosado")
        if r is not None and c is not None and "mau_real_pred_concurrent" in c.columns:
            cols = [x for x in r.columns if x not in ("fecha", "mau_prediccion_concurrent")]
            rr = r.assign(fecha=pd.to_datetime(r["fecha"])).set_index("fecha")[cols].apply(pd.to_numeric, errors="coerce").sum(axis=1)
            cc = c.assign(fecha=pd.to_datetime(c["fecha"])).set_index("fecha")["mau_real_pred_concurrent"].astype(float)
            j = pd.concat([rr, cc], axis=1, keys=["r", "c"]).dropna()
            if len(j) and (j["r"] - j["c"]).abs().max() > 1:
                add("WARN", f"desglose reactive no cuadra con concurrent (máx {(j['r'] - j['c']).abs().max():,.0f})")
        return out

    # ------------------------------------------------------------------ ejecución
    def _execute(self, op):
        if op["kind"] == "to_gbq":
            return self._orig["to_gbq"](op["df"], op["dest"], *op["args"], **op["kwargs"])
        if op["kind"] == "load":
            return self._orig["load"](op["client"], op["df"], op["table"], *op["args"], **op["kwargs"]).result()
        if op["kind"] == "dml":
            return self._orig["query"](op["client"], op["sql"], *op["args"], **op["kwargs"]).result()

    def commit_all(self, raise_on_hold: bool = True):
        t0 = time.time()
        order = list(GROUPS) + sorted({o["group"] for o in self.ops if o["group"] not in GROUPS})
        held = []
        for g in order:
            ops = [o for o in self.ops if o["group"] == g]
            if not ops:
                continue
            res = dict(group=g, tables=sorted({o["short"] for o in ops}), issues=[], status="OK", published=[])
            # duplicados 'replace' -> gana el último
            last = {}
            for i, o in enumerate(ops):
                if o["mode"] == "replace" and o["kind"] != "dml":
                    if o["short"] in last:
                        res["issues"].append(dict(level="INFO", msg=f"{o['short']} escrita más de una vez; gana la última"))
                    last[o["short"]] = i
            ops_eff = [o for i, o in enumerate(ops) if not (o["mode"] == "replace" and o["kind"] != "dml" and last[o["short"]] != i)]
            frames = {}
            for o in ops_eff:
                if o["kind"] != "dml" and o["mode"] == "replace":
                    self.staged[o["short"]] = (o["table"], o["df"])
            for o in ops_eff:
                if o["kind"] != "dml":
                    for it in self.check_table(o):
                        res["issues"].append(dict(it, table=o["short"]))
                    if o["mode"] == "replace":
                        frames[o["short"]] = o["df"]
            req = [t for t in GROUPS.get(g, []) if t not in {o["short"] for o in ops_eff}]
            if g in GROUPS and req:
                res["issues"].append(dict(level="BLOCK", msg=f"faltan tablas del grupo (no se generaron): {req}"))
            if g == "kpi_core":
                res["issues"] += self.cross_checks(frames)
            blocks = [i for i in res["issues"] if i["level"] == "BLOCK"]
            if blocks:
                res["status"] = "HOLD"
                held.append(g)
            elif self.mode == "dry_run":
                res["status"] = "OK(dry_run)"
            else:
                try:
                    for o in ops_eff:
                        if o["kind"] != "dml":
                            self._align(o)
                        self._execute(o)
                        res["published"].append(o["short"])
                except Exception as e:  # una falla de escritura a mitad de grupo debe ser visible
                    res["status"] = "ERROR"
                    res["issues"].append(dict(level="BLOCK", msg=f"falló la escritura: {type(e).__name__}: {str(e)[:200]}"))
                    held.append(g)
            self.results.append(res)
        self.report(t0)
        self.ops = []
        if held and raise_on_hold:
            raise PublishError(f"Grupos retenidos (se conserva la versión anterior): {held}. Ver reporte arriba.")
        return self.results

    def compare_with_bq(self, tol: float = 1e-6, skip=("captaciones_monitoreo_le", "pipeline_audit")):
        """Compara lo que ESTA corrida publicaría contra lo que hoy hay en BigQuery (p. ej. lo publicado por la V11
        el mismo día). Es la prueba de 'sin afectar la salida' con datos reales. Solo lectura."""
        import pandas_gbq
        rows = []
        for short, (fq, new) in sorted(self.staged.items()):
            if short in skip:
                continue
            try:
                old = pandas_gbq.read_gbq(f"SELECT * FROM `{fq}`", project_id=fq.split(".")[0], credentials=self.creds())
            except Exception as e:
                rows.append(dict(tabla=short, estado="SIN_TABLA_VIGENTE", detalle=f"{type(e).__name__}"))
                continue
            rows.append(self._cmp_frames(short, old, new, tol))
        res = pd.DataFrame(rows)
        self.log("\n" + "=" * 100 + "\n COMPARACIÓN vs BIGQUERY VIGENTE (¿la salida cambia?)\n" + "=" * 100)
        for r in rows:
            self.log(f"[{r['estado']:<12}] {r['tabla']:<40} {r.get('detalle', '')}")
        self.compare_result = res
        return res

    @staticmethod
    def _cmp_frames(short, old, new, tol):
        def norm(d):
            d = d.copy()
            for c in d.columns:
                if pd.api.types.is_datetime64_any_dtype(d[c]):
                    d[c] = d[c].dt.strftime("%Y-%m-%d")
            key = [c for c in ["fecha"] + _KEY_HELPERS if c in d.columns]
            if "fecha" in key:
                f = pd.to_datetime(d["fecha"], errors="coerce", dayfirst=True)
                d["_k"] = f.dt.strftime("%Y-%m-%d").fillna(d["fecha"].astype(str))
                key = ["_k"] + [c for c in key if c != "fecha"]
                d = d.sort_values(key, kind="stable")
            return d.reset_index(drop=True)
        try:
            a, b = norm(old), norm(new)
            det = []
            ca, cb = set(a.columns) - {"_k"}, set(b.columns) - {"_k"}
            if ca - cb:
                det.append(f"solo en BQ: {sorted(ca - cb)[:4]}")
            if cb - ca:
                det.append(f"columnas nuevas: {sorted(cb - ca)[:4]}")
            if len(a) != len(b):
                return dict(tabla=short, estado="DIFIERE", detalle=f"filas BQ={len(a)} nueva={len(b)}; " + "; ".join(det))
            bad = []
            for c in sorted(ca & cb):
                x, y = a[c], b[c]
                try:
                    xn, yn = pd.to_numeric(x, errors="raise").astype(float), pd.to_numeric(y, errors="raise").astype(float)
                    m = ~((xn.isna() & yn.isna()) | np.isclose(xn, yn, rtol=tol, atol=tol, equal_nan=True))
                except Exception:
                    m = x.astype(str).values != y.astype(str).values
                if m.any():
                    bad.append(f"{c}({int(m.sum())})")
            if bad:
                det.append(f"{len(bad)} columnas con valores distintos: {bad[:6]}")
            return dict(tabla=short, estado="DIFIERE" if bad or (ca - cb) else "IGUAL", detalle="; ".join(det))
        except Exception as e:
            return dict(tabla=short, estado="ERROR", detalle=f"{type(e).__name__}: {str(e)[:80]}")

    def report(self, t0=None):
        self.log("\n" + "=" * 100 + f"\n REPORTE DE PUBLICACIÓN | modo={self.mode} | hoy={self.today}\n" + "=" * 100)
        for r in self.results:
            self.log(f"[{r['status']:<11}] {r['group']:<14} tablas={r['tables']}")
            for i in r["issues"]:
                if i["level"] != "INFO":
                    self.log(f"      {i['level']:<5} {i.get('table', ''):<38} {i['msg']}")
        if self.report_dir:
            try:
                os.makedirs(self.report_dir, exist_ok=True)
                fn = os.path.join(self.report_dir, f"reporte_publicacion_{self.today or 'na'}.json")
                json.dump(self.results, open(fn, "w"), indent=1, default=str)
                self.log(f"[GATE] reporte guardado en {fn}")
            except Exception as e:
                self.log(f"[GATE] no se pudo guardar el reporte: {e}")


def get_pipeline_mode() -> str:
    m = os.environ.get("PIPELINE_MODE", "stage").strip().lower()
    return m if m in ("stage", "live", "dry_run") else "stage"
