"""Ejecuta un notebook Script_Diario (V11 o V12) completo, SIN credenciales ni datos reales.

    python -m forecast_hardening.dryrun.run_dryrun NOTEBOOK.ipynb --now "2026-09-15 10:00" --out /tmp/run_a

Qué hace:
  * Stubs de Colab/Drive/BigQuery/CMF + datasets sintéticos (synth.py).
  * Congela "ahora" (hora de Chile). Reloj del sistema simulado = UTC (como Colab), salvo --sys-tz.
  * Achica la grilla de XGBoost (mismo código, menos árboles) para que corra en minutos.
  * Captura TODO lo que se intentaría escribir en BigQuery y lo guarda en <out>/writes/.
  * Ejecuta celda por celda; un error NO detiene el resto (queda en <out>/cells.json).
Para notebooks V11 (sin hoy_cl()) reescribe las llamadas a reloj; con --no-rewrite exige que no queden.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import sys
import time
import traceback
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import nbformat  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import stubs  # noqa: E402

CLOCK_PATTERNS = [
    (r'pd\.Timestamp\.now\(tz="America/Santiago"\)', "DRY_NOW_CL()"),
    (r"pd\.Timestamp\.now\(\)", "DRY_NOW_SYS()"),
    (r"pd\.Timestamp\.today\(\)", "DRY_NOW_SYS()"),
    (r"datetime\.now\(tz_cl\)", "DRY_NOW_CL().to_pydatetime()"),
    (r"datetime\.date\.today\(\)", "DRY_TODAY_SYS()"),
    (r"_date_v11\.today\(\)", "DRY_TODAY_SYS()"),
    (r"_d\.today\(\)", "DRY_TODAY_SYS()"),
    (r"(?<![\w.])date\.today\(\)", "DRY_TODAY_SYS()"),
]


def rewrite_clock(src: str) -> tuple[str, int]:
    n = 0
    for pat, rep in CLOCK_PATTERNS:
        src, k = re.subn(pat, rep, src)
        n += k
    return src, n


def install_small_grid():
    from . import smallgrid

    smallgrid.install()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("notebook")
    ap.add_argument("--now", required=True, help='hora Chile, ej "2026-09-15 10:00"')
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-rewrite", action="store_true", help="exige que el notebook no use relojes directos")
    ap.add_argument("--sys-tz", default="UTC")
    ap.add_argument("--reuse-models", action="store_true")
    ap.add_argument("--only", default="", help="lista de celdas separadas por coma (default: todas)")
    ap.add_argument("--baseline-run", default="", help="corrida previa cuyas tablas se toman como 'lo vigente en BigQuery'")
    ap.add_argument("--env", action="append", default=[], help="K=V extra para el notebook")
    a = ap.parse_args(argv)

    out = Path(a.out)
    (out / "writes").mkdir(parents=True, exist_ok=True)
    now_cl = pd.Timestamp(a.now, tz="America/Santiago")
    world = stubs.install(now_cl)
    stubs.make_drive_files(now_cl.tz_localize(None).normalize(), fresh_models=not a.reuse_models)
    if a.baseline_run:
        import json as _j
        for m in _j.load(open(Path(a.baseline_run) / "writes_manifest.json")):
            if m["via"] != "client.query":
                world.baseline[str(m["table"]).split(".")[-1]] = pd.read_pickle(Path(a.baseline_run) / "writes" / m["file"])
    install_small_grid()
    os.environ["PIPELINE_NOW"] = a.now
    for kv in a.env:
        k, v = kv.split("=", 1)
        os.environ[k] = v

    sys_now = now_cl.tz_convert(a.sys_tz).tz_localize(None)
    ns = {
        "__name__": "__main__",
        "DRY_NOW_CL": lambda: now_cl,
        "DRY_NOW_SYS": lambda: sys_now,
        "DRY_TODAY_SYS": lambda: sys_now.date(),
        "display": lambda *x, **k: None,
    }

    nb = nbformat.read(a.notebook, as_version=4)
    only = {int(x) for x in a.only.split(",") if x}
    report, clock_hits = [], 0
    buf_all = io.StringIO()
    for i, c in enumerate(nb.cells):
        if c.cell_type != "code" or (only and i not in only):
            continue
        src = "\n".join(l for l in c.source.split("\n") if not l.strip().startswith(("%", "!")))
        if not a.no_rewrite:
            src, k = rewrite_clock(src)
            clock_hits += k
        else:
            for pat, _ in CLOCK_PATTERNS:
                if "def ahora_chile" not in src and re.search(pat, src):
                    report.append(dict(cell=i, status="CLOCK_VIOLATION", error=f"reloj directo: {pat}"))
        t0 = time.time()
        buf = io.StringIO()
        status, err = "ok", None
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                exec(compile(src, f"<cell {i}>", "exec"), ns)
        except BaseException as e:  # noqa
            status = "ERROR"
            err = "".join(traceback.format_exception_only(type(e), e)).strip() + "\n" + "".join(f for f in traceback.format_tb(e.__traceback__) if "<cell" in f or "site-packages" not in f)
            if isinstance(e, KeyboardInterrupt):
                raise
        buf_all.write(f"\n######## CELL {i} [{status}] ########\n{buf.getvalue()}\n")
        report.append(dict(cell=i, status=status, secs=round(time.time() - t0, 1), error=err))
        print(f"cell {i:>2} {status:5} {time.time()-t0:6.1f}s" + (f"  {err.splitlines()[0][:150]}" if err else ""), flush=True)

    (out / "stdout.log").write_text(buf_all.getvalue())
    (out / "cells.json").write_text(json.dumps(report, indent=1))
    manifest = []
    for n, wr in enumerate(world.writes):
        df = wr["df"]
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", str(wr["table"]))
        fn = f"{n:02d}_{name}.pkl"
        df.to_pickle(out / "writes" / fn)
        manifest.append(dict(n=n, table=wr["table"], rows=len(df), cols=list(df.columns), mode=wr["mode"], via=wr["via"], file=fn))
    (out / "writes_manifest.json").write_text(json.dumps(manifest, indent=1, default=str))
    (out / "reads.json").write_text(json.dumps(world.reads, indent=1, default=str))
    errs = [r for r in report if r["status"] != "ok"]
    print(f"\nclock_rewrites={clock_hits} cells={len(report)} errors={len(errs)} writes={len(world.writes)}")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
