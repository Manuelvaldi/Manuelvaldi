# Cómo ejecutar la V12 en Colab

**Notebook:** `forecast_hardening/Script_Diario_V12_blindado.ipynb`
Abrir en Colab: https://colab.research.google.com/github/Manuelvaldi/Manuelvaldi/blob/claude/bold-cray-6vqzqv/forecast_hardening/Script_Diario_V12_blindado.ipynb

## Antes de ejecutar
1. **Secreto:** en Colab (ícono de la llave) crear `CMF_API_KEY` con la key **rotada** y activar "Acceso desde el notebook".
2. **Primera celda de código ("V12 — CONFIGURACIÓN DE EJECUCIÓN")**: es la única que se edita.
   * `MODO = "dry_run"` → valida y compara contra BigQuery, **no escribe nada** (por defecto).
   * `MODO = "stage"` → publica en BigQuery al final, por grupos, solo si valida (producción).
   * `MODO = "live"` → escribe tabla por tabla como la V11 (solo si corres celdas sueltas).
   * `PERMITIR_GRUPOS_PARCIALES = "referencias"` (opcional) → si falta una tabla de ese grupo, publica igual lo que exista.
3. `Runtime > Run all`.

## Qué mirar al final
* Bloque `REPORTE DE PUBLICACIÓN`: un estado por grupo (`OK`, `OK(dry_run)` o `HOLD` con el motivo).
* En `dry_run`, además `COMPARACIÓN vs BIGQUERY VIGENTE`: `IGUAL` / `DIFIERE` por tabla. Solo es una prueba válida si BigQuery tiene lo que publicó la V11 **el mismo día** (y no en día 1 de mes).
* Si algún grupo queda `HOLD`, al final se lanza `PublishError` (esperado): los grupos sanos ya se publicaron y el retenido conserva su versión anterior.
* Reporte JSON: `.../modelos/reportes_publicacion/reporte_publicacion_AAAA-MM-DD.json`.

## Plan de puesta en marcha
1. Un día normal (día 2 en adelante): correr la V11 publicando y, el mismo día, la V12 en `dry_run`. Esperado: todo `IGUAL` salvo `forecasting_gpv_productos` (4 columnas nuevas de la V11).
2. Si sale limpio: pasar a `MODO = "stage"` y reemplazar la V11 por la V12.
3. Los primeros días, revisar el reporte final.

## Notas
* El notebook **no** contiene secretos.
* Los días 1 de mes `seguros` (falta `stock`) puede quedar retenido; no aplica si se corre desde el día 2.
* Ver `REPORTE_REVISION.md` para hallazgos, evidencias y riesgos no tocados.
