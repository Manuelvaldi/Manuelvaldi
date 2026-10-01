# forecast_hardening

Ver `REPORTE_REVISION.md` y `COMO_EJECUTAR_V12.md`.

```bash
pip install pandas==2.2.3 "numpy<2.1" xgboost scikit-learn matplotlib seaborn openpyxl nbformat pytest pyarrow requests
python -m pytest forecast_hardening/tests -q                       # 24 pruebas
python forecast_hardening/build_v12.py V11.ipynb forecast_hardening/Script_Diario_V12_blindado.ipynb
python -m forecast_hardening.dryrun.run_dryrun V11.ipynb --now "2026-09-15 10:00" --out /tmp/a
python -m forecast_hardening.dryrun.run_dryrun forecast_hardening/Script_Diario_V12_blindado.ipynb --no-rewrite --now "2026-09-15 10:00" --out /tmp/b
python -m forecast_hardening.dryrun.compare_runs /tmp/a /tmp/b --last-only
```
El notebook V11 original no se versiona aquí (contiene una API key en texto plano).
