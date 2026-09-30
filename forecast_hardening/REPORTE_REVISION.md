# Script_Diario V11 → V12 (blindado): revisión, evidencia y qué falta

Alcance: el notebook completo (87 celdas, ~10.500 líneas): captación, clientes principales, tesorería/GPV, seguros,
entrega de tarjetas, KPIs core (MAU/GPV/OB/RGU/CI-CO/ATM), revenue financiero, TMC, colocaciones y reportes.

## Qué pude y qué no pude hacer (sin maquillaje)

| | Estado |
|---|---|
| Leer y revisar todo el código, análisis estático (pyflakes) | Hecho |
| Ejecutar el notebook **completo** de punta a punta (stubs de BigQuery/Drive/Colab + datos sintéticos), en 7 escenarios de fecha | Hecho (`dryrun/`) |
| Demostrar que V12 no cambia la salida en días normales | Hecho, **sobre datos sintéticos** (ver abajo) |
| Conectarme a tus BigQuery/Drive, validar contra tablas reales, medir precisión real | **No** (no hay credenciales en este entorno) |
| Correr TimesFM con pesos reales | **No** (HuggingFace bloqueado por la red del entorno). Adaptador probado solo con un stub |

Por eso los números de "antes/después" de abajo son **de comportamiento del código**, no de precisión sobre tus datos.

## Hallazgos confirmados con el dry-run (reproducibles)

| # | Hallazgo | Evidencia | Estado en V12 |
|---|---|---|---|
| 1 | **Zona horaria mezclada.** 12 llamadas usan hora Chile y ~15 usan `date.today()` / `Timestamp.now()` / `CURRENT_DATE()` (UTC en Colab). Entre ~20–21h y medianoche de Chile, unas celdas ya están en el mes/día siguiente | Misma fecha Chile (30-sep) corrida a las 10:00 vs 21:30: **15 de 28 tablas difieren** (30 vs 31 filas, octubre mezclado, pace = NaN, `pipeline_audit` distinto) | Corregido: `hoy_chile()`; con 21:30 da **idéntico** a 10:00 |
| 2 | **Día 1 del mes (o datos atrasados): features de lag del modelo V5 quedan en 0** para el mes a proyectar (`lag_mau_mes_anterior`, `ma_3m_mes_anterior`) mientras el modelo se entrenó con ~1e5–1e11 | En datos sintéticos estables el cierre de GPV App del día 1 sale **~45% más bajo** que el de cualquier otro día (423k vs 770–870k MM); OB/MAU/CI/CO igual de afectados | Corregido (hereda el último mes observado). Meses con datos: idénticos a V11 |
| 3 | **Seguros, día 1:** si `economics` aún no tiene filas del mes nuevo, `forecasting_le_seguros` no se escribe ("vacío → no se escribe") pero `_stock` y `forecast_le_insurance` sí → tablas de un mismo grupo en meses distintos | Dry-run d01 | La compuerta retiene el grupo y lo informa. **La causa de fondo hay que verla con datos reales** (depende de si `economics` trae filas parciales de hoy) |
| 4 | **Tipos de columna inestables.** La limpieza de la celda 55 convierte float→`Int64` si "todos son enteros ese día": la misma columna cambia de FLOAT a INTEGER entre corridas | `ma_3m_mes_anterior_ci_bestado` y 2 más cambiaron de tipo entre dos días | Corregido: se alinea al esquema vigente en BigQuery |
| 5 | **Publicación no atómica entre tablas.** 28 escrituras sueltas (`to_gbq replace` = borrar y recrear); si una celda falla quedan tablas de corridas distintas. `forecasting_rgu` se escribe dos veces (celdas 40 y 61) | Conteo de escrituras en el dry-run | Compuerta por grupos (todo-o-nada por grupo) |
| 6 | **Secreto en texto plano** (API key de la CMF, celda 63) | Está en el notebook que subiste | Sacada del notebook (env `CMF_API_KEY` o Secretos de Colab). **Hay que rotarla**: ya circula en el archivo |
| 7 | **TMC solo del año 2025** (`/tmc/2025`) | Celda 63 | Ahora 2025 → año actual |
| 8 | `.pkl` se escribe sin atomicidad: una corrida cortada deja un archivo vacío y la siguiente falla con `EOFError` | Lo reproduje al fallar un dump | Escritura atómica + carga con features propias del modelo |
| 9 | RGU **borra** el modelo antes de reentrenar | Celda 40 | Respaldo `.bak` + restauración si falla |
| 10 | **Targets hardcodeados vencen**: colocaciones (hasta dic-2026), metas de principales (solo oct-26), Excel de metas por mes | Simulado feb-2027: `KeyError` críptico y el Excel sin columna | Error claro en colocaciones; el resto falla fuerte como ya hacía |
| 11 | `applymap`, `fillna(method=)`, `replace(..., inplace=True)` sobre columnas se rompen/cambian con pandas 3 | pyflakes/ejecución | Reemplazados por equivalentes |
| 12 | Re-ejecutar una celda suelta duplica transformaciones (`gpv_merged / 1e6`) | Celda 49 | Guarda que aborta con mensaje |

## Prueba de "sin afectar la salida" (A/B, 28 tablas)

`dryrun/compare_runs.py` compara valor a valor (nombres, orden, dtype, filas, valores) lo que V11 y V12 publicarían.

* V12 con todos los fixes apagados (`PIPELINE_V12_OFF=...`) y modo `live`: **0 diferencias** vs V11 → el refactor es neutro.
* V12 con fixes, días 2, 15, 30 y 31: **0 diferencias** en las 28 tablas.
* Día 1: cambian solo los KPIs que dependen de los lags (objetivo de la corrección #2).
* Noche (21:30): ahora igual a las 10:00 (#1). Dos corridas idénticas → el pipeline es determinista.

## Compuerta de publicación (`publish_gate.py`, dentro de la 1ª celda del notebook)

Modos (`PIPELINE_MODE`): **stage** (default: acumula y publica al final, por grupos, solo si valida) · **live** (como V11, con validación por tabla) · **dry_run** (valida y no escribe).
Por tabla: no vacía, sin infinitos, sin duplicados por clave, columnas y tipos compatibles con la tabla vigente, sin colapso de filas. Entre tablas (`kpi_core`): mismo mes, suma de productos = GPV App en días futuros, MAU App = subcategorías, desglose reactive cuadra. Grupos: captación, principales, tesorería, seguros, tarjetas, kpi_core, revenue financiero, referencias, colocaciones, auditoría. Un grupo retenido no bloquea a los demás; al final se levanta `PublishError` para que el job figure como fallido.

**Importante:** el default `stage` cambia *cuándo* se escribe (al final, celda nueva). Si corres celdas sueltas, usa `PIPELINE_MODE=live`. Los umbrales de los chequeos entre tablas están calibrados con datos sintéticos: parte en `dry_run` una semana y ajusta.

## Sobre TimesFM

* Usa **TimesFM 2.5** (Apache-2.0). Los pesos de 3.0 son no comerciales/no producción según el README del paquete.
* Tus propios backtests (celdas 76–83) muestran que el **cierre mensual ya es bueno** (APE 0,0–3,6% con el pace) y lo ruidoso es el **perfil diario** (MAPE ~15% en mau_app, peor los días 22–26). TimesFM puede mejorar la forma diaria y los cortes tempranos (d2/d7); no el cierre tardío, que lo manda el pace. No es plug-and-play: los picos por día del mes (1, 5, 20, fin de mes) y feriados son calendario, no periodicidad fija → conviene usar covariables (XReg) y/o un blend con el modelo actual.
* `timesfm_shadow.py` (un archivo, para Drive) mide en sombra, con la misma información al corte, contra `SeasonalNaive`, `DomProfile` (equivalente al pace), `XGBCalendar`, blends y TimesFM (con/sin covariables). `compare()` solo declara candidato si gana en ≥65% de los (mes, corte), con ≥10% de mejora relativa y ≥12 observaciones. **Nada de esto cambia producción.**
* Alternativa: BigQuery ML trae TimesFM integrado; no verifiqué la sintaxis (no tengo acceso a tu proyecto).

Colab:
```python
!pip install -q "timesfm[torch]"            # covariables: "timesfm[xreg]"
import sys; sys.path.append(directorio_salida)   # carpeta con timesfm_shadow.py
import timesfm_shadow as tsh
s = mau_app.groupby('fecha')['mau'].sum()
fc = {"actual": tsh.DomProfile(), "xgb": tsh.XGBCalendar(), "timesfm": tsh.TimesFMForecaster(),
      "timesfm_xreg": tsh.TimesFMForecaster(use_xreg=True)}
bt = tsh.run_backtest(s, fc, tsh.last_closed_months(s, 8), cutoffs=(2, 7, 14, 21))
print(tsh.summarize(bt)); print(tsh.compare(bt, "xgb", "timesfm_xreg"))
```
(Para comparar contra el método *real* del pipeline, envuelve `_refit_y_predecir` de la celda de backtest como un `Forecaster`.)

## Otros riesgos que NO toqué (cambiarían la salida; decide tú)

* Clase base `ForecastProducto` (RGU, 16 subsegmentos reactive, ATM, tesorería): `train_test_split` aleatorio + CV no temporal → "Test accuracy 0,76–0,97" inflado por fuga. V2–V5 ya lo corrigen, pero esos KPIs siguen en la base.
* `pred.astype(np.int64)` trunca y `clip(lower=1)` infla: sesgo en KPIs chicos (OB XS, ATM).
* Tesorería (celdas 7–13) guarda `.pkl` en `/shortcut-targets-by-id/...` (disco efímero, no Drive) y usa la clase sin reentreno mensual. **No** lo apunté a Drive porque esos nombres (`gpv_tc_fis`…) chocan con los `.pkl` de V5 (otras features).
* `meta=meta_gpv_top_ups` copiado a `cash_in_savings` e `investment_tyba`: las columnas `meta_*` de esos dos son de otro KPI.
* Constantes atadas al nivel del negocio (rangos 3000–3500 y clip 2500–5500 de principales, pisos de NOREM 37k/47k, reparto 12,6/87,4% de billing, `OB_CALIB_DEFAULT`, curva del revenue financiero).
* PayPal se fuerza a 0 (`applymap(lambda x: 0 ...)`); "mes objetivo" en tarjetas usa el mes de D‑1 y el resto el de hoy: el día 1 esas tablas hablan de meses distintos (por diseño V11, pero los consumidores deben saberlo).
* La celda de validación (71) corre después de subir y solo mira ATM; su "APROBADO" no frena nada.
* V2 fue peor que V1 en tu backtest (MAPE 19,0 vs 14,9) y aun así V5 va a producción sin un backtest V5-vs-V1 sistemático.

## Qué necesito de ti para cerrar el círculo

1. **Rotar la API key de la CMF** y cargarla como secreto `CMF_API_KEY`.
2. Correr V12 en Colab con `PIPELINE_MODE=dry_run` (reporte en `.../modelos/reportes_publicacion/`) y pasarme el reporte, o darme acceso de solo lectura / exports de `modelos_forecasting_*` y `INFORMATION_SCHEMA.COLUMNS` de `kpitos` para validar contra datos reales.
3. Habilitar `huggingface.co` en el entorno (o correr el shadow en Colab) para medir TimesFM de verdad.
4. Decidir el modo por defecto (`stage` vs `live`).

## Archivos

* `Script_Diario_V12_blindado.ipynb` — notebook (sin salidas; primera celda = helper V12, última = publicación). Se regenera con `build_v12.py` (reemplazos con conteo exacto; falla si el fuente cambia).
* `publish_gate.py`, `timesfm_shadow.py` — módulos.
* `dryrun/` — stubs, datos sintéticos, runner, `compare_runs.py`, `landing_summary.py`. Uso: `python -m forecast_hardening.dryrun.run_dryrun NOTEBOOK --now "2026-09-15 10:00" --out DIR`.
* `tests/` — 24 pruebas (compuerta con inyección de fallas, parches, shadow).
