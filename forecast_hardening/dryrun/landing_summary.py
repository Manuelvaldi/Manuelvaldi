"""Resumen de 'landing' (cierre de mes proyectado) por corrida, para ver saltos entre escenarios."""
import sys
from pathlib import Path

import pandas as pd

from .compare_runs import load


def pick(d, table, col):
    fr = d.get(table)
    if not fr:
        return None
    df = fr[-1]
    return float(pd.to_numeric(df[col], errors="coerce").sum()) if col in df.columns else None


def main(runs):
    rows = []
    for r in runs:
        d = load(r)
        rows.append({
            "run": Path(r).name.replace("run_", ""),
            "gpv_app_MM": (pick(d, "kpitos.forecasting_gpv_app", "gpv_real_pred") or float("nan")) / 1e6,
            "mau_app": pick(d, "kpitos.forecasting_categorias", "mau_real_pred_app"),
            "mau_subcats": pick(d, "kpitos.forecasting_categorias", "mau_prediccion_app_2"),
            "rgu_LE": float(d["kpitos.forecasting_rgu"][-1]["rgu_cierre_mensual_estimado"].iloc[0]) if "kpitos.forecasting_rgu" in d else None,
            "ob_large": pick(d, "kpitos.forecasting_ob_tc", "ob_real_pred_large"),
            "filas_gpv_app": len(d["kpitos.forecasting_gpv_app"][-1]) if "kpitos.forecasting_gpv_app" in d else None,
        })
    print(pd.DataFrame(rows).round(1).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1:])
