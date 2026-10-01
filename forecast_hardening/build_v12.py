"""Construye Script_Diario_V12_blindado.ipynb a partir de la V11 aplicando parches quirúrgicos.

    python forecast_hardening/build_v12.py SRC_V11.ipynb OUT_V12.ipynb

Cada parche es un reemplazo de texto con número de ocurrencias EXACTO (si el notebook fuente
cambia y no calza, el build falla en vez de parchear a ciegas). Todos los parches que tocan
lógica numérica cuelgan de V12_FIXES y se pueden apagar uno a uno (PIPELINE_V12_OFF=a,b,c) para
demostrar que, apagados, la salida es idéntica a la V11 (ver dryrun/compare_runs.py).
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import nbformat

HERE = Path(__file__).resolve().parent

# --------------------------------------------------------------------------- helper cell (V12)
HELPER = r'''# ==============================================================================
# V12 — BLINDAJE (ejecutar PRIMERO). Reloj único de Chile, compuerta de publicación y helpers.
# ------------------------------------------------------------------------------
# * hoy_chile()/ahora_chile(): UNA sola fuente de "hoy" (America/Santiago). Colab corre en UTC y
#   date.today()/Timestamp.now() sin zona saltaban de mes/día 3-4 h antes que Chile (entre las
#   20-21h y medianoche): tablas con meses mezclados. PIPELINE_NOW="YYYY-MM-DD HH:MM" fuerza la
#   fecha (reprocesos/pruebas).
# * GATE: intercepta pandas_gbq.to_gbq / bigquery load / DELETE del monitoreo. Modo (env
#   PIPELINE_MODE): dry_run (DEFAULT: valida y NO escribe nada) | stage (publica todo al final,
#   por grupos, si valida) | live (como V11, con validación por tabla). Escribir exige pedirlo.
# * V12_FIXES: cada corrección de lógica se puede apagar con PIPELINE_V12_OFF=nombre1,nombre2.
# ==============================================================================
import os, pickle, tempfile
import numpy as np
import pandas as pd

_OFF = {x.strip() for x in os.environ.get("PIPELINE_V12_OFF", "").split(",") if x.strip()}
V12_FIXES = {k: (k not in _OFF) for k in ["lag_mes_sin_datos", "tmc_anios", "pkl_atomico", "rgu_pkl_respaldo",
                                          "reloj_unico", "guardas_idempotencia"]}

def ahora_chile():
    """Timestamp tz-aware America/Santiago (o el forzado por PIPELINE_NOW)."""
    ov = os.environ.get("PIPELINE_NOW", "").strip()
    if ov:
        return pd.Timestamp(ov, tz="America/Santiago")
    return pd.Timestamp.now(tz="America/Santiago")

def hoy_chile():
    """Medianoche naive de la fecha de hoy en Chile."""
    return ahora_chile().tz_localize(None).normalize()

def ahora_utc_naive():
    """Instante actual en UTC naive (solo para marcas de auditoría; igual que Timestamp.now() en Colab)."""
    return ahora_chile().tz_convert("UTC").tz_localize(None)

def _dump_pickle_atomic(obj, path):
    """Escribe el .pkl a un temporal y lo reemplaza de una vez: una corrida cortada ya no deja un
    archivo vacío/corrupto (EOFError al siguiente load)."""
    if not V12_FIXES.get("pkl_atomico", True):
        pickle.dump(obj, open(path, "wb")); return
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            pickle.dump(obj, f)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise

def _columnas_del_modelo(model):
    """Nombres de features con los que se ENTRENÓ el modelo (None si no se pueden leer)."""
    est = getattr(model, "best_estimator_", model)
    for getter in (lambda e: e.feature_names_in_, lambda e: e.regressor_.feature_names_in_,
                   lambda e: e.get_booster().feature_names, lambda e: e.regressor_.get_booster().feature_names):
        try:
            v = getter(est)
            if v is not None and len(v):
                return [str(x) for x in v]
        except Exception:
            pass
    return None

# ---- compuerta de publicación (código de forecast_hardening/publish_gate.py, inline) ----
@@PUBLISH_GATE@@

GATE = PublishGate(mode=get_pipeline_mode(), today=hoy_chile().date(),
                   allow_schema_drift=os.environ.get("PIPELINE_ALLOW_SCHEMA_DRIFT", "") == "1",
                   credentials_getter=lambda: globals().get("credentials")).install()
print(f"[V12] hoy_chile={hoy_chile().date()} | modo={GATE.mode} | fixes_off={sorted(_OFF) or '-'}")
'''

CONFIG_CELL = r'''# ==============================================================================
# V12 — CONFIGURACIÓN DE EJECUCIÓN  (EDITA SOLO ESTA CELDA y luego Runtime > Run all)
# ==============================================================================
import os

MODO = "dry_run"
#   "dry_run" = valida y compara contra BigQuery, NO escribe nada            <- seguro (recomendado para probar)
#   "stage"   = publica en BigQuery al final, por grupos, solo si valida      <- producción
#   "live"    = escribe tabla por tabla como la V11 (para correr celdas sueltas)

PERMITIR_GRUPOS_PARCIALES = ""
#   Grupos donde, si falta una tabla, se publica igual lo que exista. Ej: "referencias". Vacío = todo-o-nada.

# --------------------------------------------------------------------------------------------------
os.environ["PIPELINE_MODE"] = os.environ.get("PIPELINE_MODE_FORCE", MODO)
os.environ["PIPELINE_ALLOW_PARTIAL"] = PERMITIR_GRUPOS_PARCIALES

try:                                    # el secreto de la CMF (no se imprime)
    from google.colab import userdata
    _cmf_ok = bool(os.environ.get("CMF_API_KEY") or userdata.get("CMF_API_KEY"))
except Exception:
    _cmf_ok = bool(os.environ.get("CMF_API_KEY"))

print("=" * 78)
print(f" MODO = {os.environ['PIPELINE_MODE']}   |   grupos parciales = {PERMITIR_GRUPOS_PARCIALES or '-'}")
print(f" Secreto CMF_API_KEY: {'OK' if _cmf_ok else 'FALTA (Secretos de Colab; sin él la celda de TMC falla)'}")
if os.environ["PIPELINE_MODE"] != "dry_run":
    print(" !!!! ESTA CORRIDA ESCRIBE EN BIGQUERY !!!!")
else:
    print(" Modo seguro: no se escribe nada en BigQuery (la compuerta solo valida y compara).")
print("=" * 78)
'''

COMMIT_CELL = r'''# ==============================================================================
# V12 — PUBLICACIÓN FINAL (ejecutar al FINAL). Valida y publica los grupos de tablas.
# stage: aquí se escribe en BigQuery, grupo por grupo. Un grupo con error se retiene completo
#        (se conserva la versión anterior y consistente) y al final se levanta PublishError.
# dry_run: solo reporte. live: ya se publicó tabla por tabla; esto solo imprime el reporte.
# ==============================================================================
try:
    GATE.report_dir = f"{directorio_salida}/reportes_publicacion"
except NameError:
    pass
GATE.commit_all()
if GATE.mode == "dry_run":
    GATE.compare_with_bq()   # solo lectura: compara lo que se publicaría vs lo vigente en BigQuery
'''

MD_NOTE = """

---
## V12 (blindaje) — cambios vs V11
Ver `forecast_hardening/REPORTE_REVISION.md`. Resumen: reloj único de Chile (`hoy_chile()`), compuerta de
publicación por grupos con chequeos entre tablas (`GATE`, modo `PIPELINE_MODE`=stage|live|dry_run),
corrección de features de lag del modelo V5 cuando el mes aún no tiene datos (día 1), escritura atómica de
`.pkl`, secreto de la CMF fuera del notebook, TMC con año actual, guardas de re-ejecución.
Primera celda de código = configuración (única que se edita); luego el helper V12; la última = publicación."""


class Patcher:
    def __init__(self, nb):
        self.nb = nb
        self.log = []

    def rep(self, ci, old, new, count=1, regex=False, tag=""):
        c = self.nb.cells[ci]
        src = c.source
        n = len(re.findall(old, src)) if regex else src.count(old)
        if n != count:
            raise SystemExit(f"[build_v12] celda {ci}: '{old[:60]}...' aparece {n} veces (esperado {count})")
        c.source = re.sub(old, new, src) if regex else src.replace(old, new)
        self.log.append((ci, tag or old[:50].replace("\n", " "), n))


def build(src_path, out_path):
    nb = nbformat.read(src_path, as_version=4)
    nbformat.validator.normalize(nb)
    p = Patcher(nb)
    code = lambda i: nb.cells[i].cell_type == "code"

    # ------------------------------------------------------------- A. reloj único
    clock = [
        (r'pd\.Timestamp\.now\(tz="America/Santiago"\)', "ahora_chile()"),
        (r"datetime\.now\(tz_cl\)", "ahora_chile().to_pydatetime()"),
        (r"datetime\.date\.today\(\)", "hoy_chile().date()"),
        (r"_date_v11\.today\(\)", "hoy_chile().date()"),
        (r"_d\.today\(\)", "hoy_chile().date()"),
        (r"(?<![\w.])date\.today\(\)", "hoy_chile().date()"),
    ]
    for i, c in enumerate(nb.cells):
        if not code(i):
            continue
        s = c.source
        if 'df_audit["ts_corrida"] = pd.Timestamp.now()' in s:
            s = s.replace('df_audit["ts_corrida"] = pd.Timestamp.now()', 'df_audit["ts_corrida"] = ahora_utc_naive()')
        s = s.replace("pd.Timestamp.today().normalize()", "hoy_chile()")
        s = s.replace("pd.Timestamp.now().normalize()", "hoy_chile()")
        for pat, rep in clock:
            s = re.sub(pat, rep, s)
        s = s.replace("CURRENT_DATE() - 1", 'DATE_SUB(CURRENT_DATE("America/Santiago"), INTERVAL 1 DAY)')
        s = s.replace("CURRENT_DATE()-1", 'DATE_SUB(CURRENT_DATE("America/Santiago"), INTERVAL 1 DAY)')
        s = s.replace("DATE_SUB(CURRENT_DATE,INTERVAL 1 DAY)", 'DATE_SUB(CURRENT_DATE("America/Santiago"),INTERVAL 1 DAY)')
        if s != c.source:
            p.log.append((i, "reloj", 1))
            c.source = s
    # verificación: no debe quedar ningún reloj directo
    left = []
    for i, c in enumerate(nb.cells):
        if code(i):
            for m in re.finditer(r"(?<![\w.])(?:pd\.)?Timestamp\.(?:now|today)\(|(?<![\w.])date\.today\(|\.fromtimestamp|CURRENT_DATE(?!\([\"\']America)", c.source):
                left.append((i, c.source[m.start():m.start() + 40]))
    left = [x for x in left if "fromtimestamp" not in x[1]]
    if left:
        raise SystemExit(f"[build_v12] relojes directos sin parchear: {left}")

    # ------------------------------------------------------------- B. secreto CMF + TMC por año
    c63 = [i for i, c in enumerate(nb.cells) if code(i) and "api_key_cmf" in c.source]
    assert len(c63) == 1, c63
    i = c63[0]
    old_head = nb.cells[i].source.split("response = response[response['Fecha']")[0]
    new_head = '''import os
api_key_cmf = os.environ.get("CMF_API_KEY")
if not api_key_cmf:
    try:
        from google.colab import userdata
        api_key_cmf = userdata.get("CMF_API_KEY")
    except Exception:
        api_key_cmf = None
if not api_key_cmf:
    raise RuntimeError("Falta CMF_API_KEY (variable de entorno o Secretos de Colab). La key ya NO va en el notebook.")

_anios = range(2025, hoy_chile().year + 1) if V12_FIXES.get("tmc_anios", True) else [2025]
_tmcs = []
for _y in _anios:
    try:
        _r = requests.get(f'https://api.cmfchile.cl/api-sbifv3/recursos_api/tmc/{_y}?apikey={api_key_cmf}&formato=json', timeout=60)
        _r.raise_for_status()
        _tmcs += _r.json()['TMCs']
    except Exception as _e:
        if _y == _anios[0]:
            raise
        print(f"[V12 TMC] !! no se pudo leer {_y}: {type(_e).__name__}: {str(_e)[:80].replace(api_key_cmf, '***')}")
response = pd.json_normalize(_tmcs)
response = response.drop_duplicates(subset=['Fecha', 'Hasta', 'SubTitulo', 'Tipo'] if 'Tipo' in response.columns else ['Fecha', 'Hasta', 'SubTitulo'])
response['Valor'] = response['Valor'].astype(np.float64)
response['Valor'] = response['Valor']/100
response['Fecha'] = pd.to_datetime(response['Fecha'], format='%Y-%m-%d')
response['Hasta'] = pd.to_datetime(response['Hasta'], format='%Y-%m-%d')
'''
    nb.cells[i].source = nb.cells[i].source.replace(old_head, new_head)
    p.log.append((i, "CMF key a env/secretos + TMC por año", 1))

    # ------------------------------------------------------------- C. V5: lag features del mes sin datos
    ci = [i for i, c in enumerate(nb.cells) if code(i) and "class ForecastProductoV5" in c.source]
    assert len(ci) == 1
    p.rep(ci[0], """        df['periodo'] = df['fecha'].dt.to_period('M').astype(str)
        df = df.merge(""", """        df['periodo'] = df['fecha'].dt.to_period('M').astype(str)
        # V12: un mes SIN dias observados (dia 1, o datos atrasados) no tenia fila en `mensual` y sus
        # features de lag quedaban en 0 (el modelo se entreno con ~1e5-1e11) -> cierre ~50% bajo.
        # Ahora hereda el ultimo mes observado anterior. Meses CON datos: identicos a V11.
        _faltan = sorted(set(df['periodo']) - set(mensual['periodo']))
        if V12_FIXES.get('lag_mes_sin_datos', True) and _faltan:
            _filas = []
            for _p in _faltan:
                _prev = mensual.loc[mensual['periodo'] < _p, 'mau_mes_total']
                if len(_prev):
                    _filas.append({'periodo': _p, 'lag_mau_mes_anterior': float(_prev.iloc[-1]),
                                   'ma_3m_mes_anterior': float(_prev.tail(3).mean())})
            if _filas:
                mensual = pd.concat([mensual, pd.DataFrame(_filas)], ignore_index=True)
        df = df.merge(""", tag="V5 lag features")

    # ------------------------------------------------------------- D. pickles atomicos + carga robusta
    for i, c in enumerate(nb.cells):
        if not code(i):
            continue
        if "pickle.dump(grid, open(filename, 'wb'))" in c.source:
            n = c.source.count("pickle.dump(grid, open(filename, 'wb'))")
            p.rep(i, "pickle.dump(grid, open(filename, 'wb'))", "_dump_pickle_atomic(grid, filename)", count=n, tag="pkl atomico")
        if "            except:\n                self._entrenar_modelo()" in c.source:
            p.rep(i, """                self.model_columns = temp_X.columns.tolist()
            except:
                self._entrenar_modelo()""", """                self.model_columns = temp_X.columns.tolist()
                # V12: si el pkl trae sus propias features, usarlas (un pkl de otra version/feature-set
                # ya no rompe el predict; las faltantes se rellenan con 0 en reindex).
                _mc = _columnas_del_modelo(self.model)
                if _mc:
                    self.model_columns = _mc
            except Exception as _e:
                print(f"[V12] pkl ausente/ilegible ({type(_e).__name__}): re-entrenando {self.nombre_algoritmo}")
                self._entrenar_modelo()""", tag="carga robusta pkl")

    # ------------------------------------------------------------- E. RGU: respaldo del pkl en vez de borrarlo
    cr = [i for i, c in enumerate(nb.cells) if code(i) and "os.remove(ruta_modelo_rgu)" in c.source]
    assert len(cr) == 1
    p.rep(cr[0], """if os.path.exists(ruta_modelo_rgu):
    os.remove(ruta_modelo_rgu)""", """_bak_rgu = ruta_modelo_rgu + ".bak"
if os.path.exists(ruta_modelo_rgu):
    if V12_FIXES.get("rgu_pkl_respaldo", True):
        os.replace(ruta_modelo_rgu, _bak_rgu)   # V12: se respalda; si el re-entreno falla se restaura
    else:
        os.remove(ruta_modelo_rgu)""", tag="rgu pkl respaldo")
    p.rep(cr[0], """forecast_rgu = forecast_rgu.proyectar(rgu_historico)
""", """try:
    forecast_rgu = forecast_rgu.proyectar(rgu_historico)
except BaseException:
    if os.path.exists(_bak_rgu) and not os.path.exists(ruta_modelo_rgu):
        os.replace(_bak_rgu, ruta_modelo_rgu)
    raise
else:
    if os.path.exists(_bak_rgu):
        os.remove(_bak_rgu)
""", tag="rgu proyectar con restauracion")

    # ------------------------------------------------------------- F. guardas de re-ejecucion / pandas futuro
    cg = [i for i, c in enumerate(nb.cells) if code(i) and "gpv_merged.iloc[:, 1:] = gpv_merged.iloc[:, 1:] / 1000000" in c.source]
    assert len(cg) == 1
    p.rep(cg[0], "gpv_merged.iloc[:, 1:] = gpv_merged.iloc[:, 1:] / 1000000",
          """if V12_FIXES.get("guardas_idempotencia", True) and globals().get("_V12_GPV_ESCALADO"):
    raise RuntimeError("[V12] gpv_merged ya se dividio por 1e6 en esta sesion: re-ejecuta el notebook desde el inicio (no solo esta celda).")
gpv_merged.iloc[:, 1:] = gpv_merged.iloc[:, 1:] / 1000000
_V12_GPV_ESCALADO = True""", tag="guarda division 1e6")
    p.rep([i for i, c in enumerate(nb.cells) if code(i) and "gpv_investment_tyba['gpv'].replace" in c.source][0],
          "gpv_investment_tyba['gpv'].replace({0:0.000000000000001},inplace=True)",
          "gpv_investment_tyba['gpv'] = gpv_investment_tyba['gpv'].replace({0:0.000000000000001})", tag="replace inplace")
    p.rep([i for i, c in enumerate(nb.cells) if code(i) and "suma_bruta_submodelos'].replace(0, 1, inplace=True)" in c.source][0],
          "df_final_reactive['suma_bruta_submodelos'].replace(0, 1, inplace=True)",
          "df_final_reactive['suma_bruta_submodelos'] = df_final_reactive['suma_bruta_submodelos'].replace(0, 1)", tag="replace inplace")
    p.rep([i for i, c in enumerate(nb.cells) if code(i) and ".fillna(method='ffill')" in c.source][0],
          ".fillna(method='ffill')", ".ffill()", tag="fillna(method)")
    # applymap -> map (DataFrame.map existe desde pandas 2.1; applymap se elimina en 3.0; mismo resultado)
    for i, c in enumerate(nb.cells):
        if code(i) and ".applymap(lambda x: 0 if pd.notnull(x) else 0)" in c.source:
            n = c.source.count(".applymap(lambda x: 0 if pd.notnull(x) else 0)")
            p.rep(i, ".applymap(lambda x: 0 if pd.notnull(x) else 0)", ".map(lambda x: 0)", count=n, tag="applymap->map")

    # ------------------------------------------------------------- G. colocaciones: targets vencidos = error claro
    cc = [i for i, c in enumerate(nb.cells) if code(i) and "fecha_fin    = max(targets.keys())" in c.source]
    assert len(cc) == 1
    p.rep(cc[0], "fechas_proy  = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')",
          """if fecha_fin < fecha_inicio:
    raise RuntimeError(f"[V12] Los targets mensuales hardcodeados terminan en {fecha_fin.date()} y el ultimo real es "
                       f"{fecha_max.date()}: cargar los targets del periodo siguiente (celda 'TARGETS MENSUALES').")
fechas_proy  = pd.date_range(start=fecha_inicio, end=fecha_fin, freq='D')""", tag="targets vencidos")

    # ------------------------------------------------------------- G2. dia 1: columna real toda NA (Int64) rompia la heuristica
    cu = [i for i, c in enumerate(nb.cells) if code(i) and "def convertir_a_clp_seguro" in c.source]
    assert len(cu) == 1
    p.rep(cu[0], """    promedio = df[col_name].mean()""",
          """    # V12: en el dia 1 la columna REAL del mes viene toda NA (Int64): mean() = <NA> y `<NA> > x` lanzaba
    # TypeError. Se pasa a float (NaN) y se compara solo si hay dato; sin dato la conversion deja NA igual.
    promedio = pd.to_numeric(df[col_name], errors="coerce").astype(float).mean()""", tag="dia1 NA en conversion CLP")
    p.rep(cu[0], "    if promedio > 500000:", "    if pd.notna(promedio) and promedio > 500000:", tag="dia1 NA en conversion CLP")

    # ------------------------------------------------------------- H. helper (1ra celda) + commit (ultima) + nota md
    gate_src = (HERE / "publish_gate.py").read_text()
    gate_src = gate_src.replace("from __future__ import annotations\n", "")
    gate_src = re.sub(r'^""".*?"""\n', "", gate_src, count=1, flags=re.S)
    helper = HELPER.replace("@@PUBLISH_GATE@@", gate_src)
    first_code = next(i for i, c in enumerate(nb.cells) if code(i))
    nb.cells.insert(first_code, nbformat.v4.new_code_cell(helper))
    nb.cells.insert(first_code, nbformat.v4.new_code_cell(CONFIG_CELL))   # queda ANTES del helper
    nb.cells.append(nbformat.v4.new_code_cell(COMMIT_CELL))
    nb.cells[0].source = nb.cells[0].source.replace("Script_Diario V11 (30-09-2026)", "Script_Diario V12 blindado (base V11 30-09-2026)") + MD_NOTE
    # sin outputs (la V11 trae 1.8 MB de salidas de una corrida real)
    for c in nb.cells:
        if c.cell_type == "code":
            c.outputs, c.execution_count = [], None
    nbformat.validator.normalize(nb)
    nbformat.write(nb, out_path)
    return p.log


if __name__ == "__main__":
    log = build(sys.argv[1], sys.argv[2])
    for row in log:
        print("patch", row)
    print(f"OK -> {sys.argv[2]}")
