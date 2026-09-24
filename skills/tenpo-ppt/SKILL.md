---
name: tenpo-ppt
description: Crea presentaciones PowerPoint (.pptx) con la identidad visual de Tenpo (fintech chilena) — portada, agenda, KPIs, gráficos nativos, tablas, comparativos, timelines y cierre, con colores, tipografía, formato numérico chileno y estilo de títulos de la marca. Úsala siempre que el usuario pida una ppt, presentación, deck, láminas o slides para Tenpo, para su equipo, gerencia o directorio en Tenpo, o que mencione Tenpo junto con presentar resultados, métricas (GPV, cartera, TC, prepago, CMF, créditos), un modelo financiero o un reporte — aunque no diga "marca" ni "template". También úsala para "pasar a ppt" un Excel, Sheet o análisis de Tenpo.
---

# Tenpo PPT

Genera decks `.pptx` con marca Tenpo usando la librería `scripts/tenpo.js` (sobre `pptxgenjs`). La librería ya resuelve colores, tipografía, márgenes, footer, logo y los layouts. Tu trabajo es **el contenido y la historia**, no dibujar cajas.

Esta skill se apoya en la skill `pptx` para los detalles técnicos (gotchas de pptxgenjs, validación y QA visual). Si está disponible, léela para la sección de QA.

## Flujo

1. **Entiende la audiencia y el mensaje.** Un deck para directorio es corto y de conclusiones. Uno para el equipo puede tener más detalle. Si los datos vienen de un Excel/Sheet/Drive, léelos primero y usa cifras reales. No inventes números: si falta un dato, pon "pend." o pregúntalo.
2. **Arma el guion antes de programar.** Una idea por lámina. Escribe el título de cada lámina como una **conclusión** ("La cartera TC creció 32% en 6 meses"), no como un tema ("Cartera TC"). Así el deck se entiende leyendo solo los títulos.
3. **Escribe un script Node** que haga `require` de `scripts/tenpo.js` (ruta absoluta a esta skill) y llame a los layouts. Parte copiando `scripts/example_deck.js`, que usa todos los layouts.
4. **Genera, valida y revisa visualmente** (ver QA). Corrige y vuelve a generar.
5. Entrega el `.pptx`.

```bash
# si require('pptxgenjs') falla: npm install pptxgenjs en un directorio de trabajo y usa NODE_PATH
NODE_PATH=$PWD/node_modules node mi_deck.js
```

## Layouts disponibles

Todos reciben `deck` como primer argumento. `kicker` es una etiqueta corta en mayúsculas sobre el título; `source` va al pie ("Fuente: ..."); `notes` va a las notas del orador.

| Función | Cuándo usarla | Parámetros clave |
|---|---|---|
| `cover` | Primera lámina | `title, subtitle, area, date` |
| `agenda` | Decks de 6+ láminas | `items[]` (3–6) |
| `section` | Separar bloques en decks largos | `number, title, subtitle` |
| `kpis` | 2–4 cifras principales | `items[{value, label, delta?, good?, note?}]` |
| `chart` | Tendencias, comparaciones, composición | `type` (col, bar, line, area, pie, doughnut), `series[{name, labels, values}]`, `takeaways[]`, `numFmt`, `stacked` |
| `table` | Detalle por producto/país/mes (≤ 10 filas) | `header[], rows[][]` (strings ya formateados), `highlightRow`, `colW[]` |
| `twoColumn` | A vs B, antes/después, interno vs regulador | `left/right {heading, bullets[]}` |
| `content` | Argumento en bullets + una cifra clave | `bullets[]` (≤ 5), `highlight {value, text}` |
| `steps` | Proceso o plan de 3–6 pasos | `items[{title, text}]` |
| `closing` | Última lámina: próximos pasos | `items[]`, `contact` |

Para algo que no calza en ningún layout, usa `T.newSlide(deck)`, `T.header(slide, {title})`, `T.footer(deck, slide, {source})` y dibuja con `slide.addShape/addText` usando los colores de `T.BRAND`. No hardcodees colores fuera de `BRAND`.

## Reglas de marca

Los detalles están en `references/brand.md`. Lo esencial:

- **Paleta:** el turquesa Tenpo es el acento principal y el azul noche es la base oscura. Portada, secciones y cierre van en fondo oscuro, y el contenido en blanco. Verde y rojo solo para variaciones positivas o negativas.
- **Motivo:** círculos turquesa en láminas oscuras y tarjetas con esquinas redondeadas en las claras. No uses barras de color ni líneas bajo los títulos.
- **Idioma y tono:** español de Chile, directo y sin jerga innecesaria. Siglas de negocio tal cual (GPV, TC, TP, CMF, MM).
- **Números:** punto para miles y coma para decimales (`$67.512 MM`, `21,6%`). Usa `T.fmt`:
  - `fmt.clpMM(67512000000)` → `$67.512 MM`
  - `fmt.pct(0.216)` → `21,6%`
  - `fmt.pp(1.3)` → `+1,3 pp`
  - `fmt.delta(0.058)` → `▲ 5,8%`
  - `fmt.num(360600)` → `360.600`
- **"MM" = millones.** Indica siempre la moneda (CLP `$` o `US$`) y el período ("feb-26", "Q3 2026", "últimos 12 meses").
- **Siempre fuente** en láminas con datos (`source`).

## Buenas prácticas de contenido

- 8–12 láminas para un reporte típico. Si hay más, usa `section` y `agenda`.
- Máximo 5 bullets por lámina y una línea cada uno. Si no cabe, divide la lámina.
- Varía los layouts. No pongas tres láminas de bullets seguidas: convierte cifras en `kpis`, series en `chart` y comparaciones en `twoColumn`.
- En los gráficos, usa el título para la conclusión y `takeaways` para 2–3 hallazgos. Usa `numFmt` (`"#,##0"`, `"#,##0.0"`, `"0.0%"`); PowerPoint aplica el separador según la configuración regional del usuario.
- Para evolución mensual usa `line` o `col`. Para ranking usa `bar` (horizontal). `pie` y `doughnut` solo con 2–5 partes.

## QA (obligatorio)

```bash
python <pptx-skill>/scripts/office/validate.py deck.pptx
python <pptx-skill>/scripts/office/soffice.py --headless --convert-to pdf --outdir $PWD $PWD/deck.pptx
# luego renderiza el PDF a PNG (pdftoppm o pymupdf) y mira cada lámina
```

Revisa que no haya texto cortado o encimado, cifras mal formateadas (con punto decimal), láminas sin fuente ni placeholders olvidados. Si LibreOffice dice "source file could not be loaded", falta `libreoffice-impress` (`apt-get install -y libreoffice-impress`).

## Logo

Si existen `assets/logo.png` (para fondo claro) y `assets/logo-white.png` (para fondo oscuro), la librería los usa. Si no existen, dibuja el wordmark "tenpo" en texto turquesa. Si el usuario comparte el logo oficial, guárdalo ahí.
