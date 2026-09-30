"""Compara dos corridas del dry-run tabla por tabla.

    python -m forecast_hardening.dryrun.compare_runs RUN_A RUN_B [--tol 1e-9]

Para cada tabla publicada por ambas: mismas columnas (nombre/orden/dtype), mismas filas y mismos
valores. Reporta las diferencias para que 'sin afectar la salida' sea verificable y no una promesa.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def load(run):
    run = Path(run)
    man = json.load(open(run / "writes_manifest.json"))
    out = {}
    for m in man:
        out.setdefault(m["table"], []).append(pd.read_pickle(run / "writes" / m["file"]))
    return out


def cmp_frames(a: pd.DataFrame, b: pd.DataFrame, tol: float):
    issues = []
    if list(a.columns) != list(b.columns):
        only_a = [c for c in a.columns if c not in b.columns]
        only_b = [c for c in b.columns if c not in a.columns]
        issues.append(f"columnas: solo A={only_a[:8]} solo B={only_b[:8]} (orden distinto={set(a.columns)==set(b.columns)})")
    cols = [c for c in a.columns if c in b.columns]
    if len(a) != len(b):
        issues.append(f"filas A={len(a)} B={len(b)}")
        return issues
    for c in cols:
        if str(a[c].dtype) != str(b[c].dtype):
            issues.append(f"dtype {c}: {a[c].dtype} vs {b[c].dtype}")
        x, y = a[c].reset_index(drop=True), b[c].reset_index(drop=True)
        try:
            xn, yn = pd.to_numeric(x, errors="raise").astype(float), pd.to_numeric(y, errors="raise").astype(float)
            bad = ~((xn.isna() & yn.isna()) | np.isclose(xn, yn, rtol=tol, atol=tol, equal_nan=True))
        except Exception:
            bad = ~((x.astype(str) == y.astype(str)))
        if bad.any():
            i = int(np.argmax(bad.values))
            issues.append(f"valores {c}: {int(bad.sum())} difieren (ej fila {i}: {x.iloc[i]!r} vs {y.iloc[i]!r})")
    return issues


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--last-only", action="store_true", help="si una tabla se escribe varias veces, comparar solo la última")
    ap.add_argument("--ignore", default="<DML>", help="tablas a ignorar, separadas por coma")
    x = ap.parse_args(argv)
    A, B = load(x.a), load(x.b)
    ign = set(x.ignore.split(","))
    if x.last_only:
        A = {k: v[-1:] for k, v in A.items()}
        B = {k: v[-1:] for k, v in B.items()}
    bad = 0
    for t in sorted(set(A) | set(B)):
        if t in ign:
            continue
        if t not in A or t not in B:
            print(f"[SOLO {'A' if t in A else 'B'}] {t}")
            bad += 1
            continue
        if len(A[t]) != len(B[t]):
            print(f"[DIFF] {t}: nº de escrituras A={len(A[t])} B={len(B[t])}")
            bad += 1
        for k, (fa, fb) in enumerate(zip(A[t], B[t])):
            iss = cmp_frames(fa, fb, x.tol)
            if iss:
                bad += 1
                print(f"[DIFF] {t}#{k}")
                for s in iss[:6]:
                    print("    -", s)
            else:
                print(f"[IGUAL] {t}#{k}  ({len(fa)}x{fa.shape[1]})")
    print(f"\nTablas con diferencias: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
