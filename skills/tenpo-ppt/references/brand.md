# Marca Tenpo: tokens para presentaciones

> **Estado:** los valores son una aproximación de la identidad pública de Tenpo (turquesa + azul noche, wordmark "tenpo" en minúsculas). Si tienes el manual de marca oficial, reemplaza los hex en `scripts/tenpo.js` (objeto `BRAND`) y en esta tabla. No hace falta cambiar nada más.

## Colores

| Token | Hex | Uso |
|---|---|---|
| `primary` | `00BFA5` | Acento principal: círculos, números de pasos, 1.ª serie de gráficos, cifras destacadas sobre fondo oscuro |
| `primaryDark` | `00897B` | Texto turquesa sobre blanco (kickers, cifras en tarjetas claras), por contraste |
| `primaryLight` | `E0F7F4` | Fondo de tarjetas destacadas y de la fila resaltada en tablas |
| `ink` | `0F1B2D` | Fondo de portada, secciones y cierre; títulos; header de tablas |
| `text` | `1F2933` | Texto de cuerpo |
| `muted` | `6B7785` | Captions, fuentes, ejes, etiquetas de KPI |
| `line` | `D9DEE3` | Grillas y bordes |
| `bgSoft` | `F4F6F8` | Tarjetas neutras y filas cebra |
| `positive` / `negative` / `warning` | `12B76A` / `F04438` / `F79009` | Solo variaciones y alertas |

Serie de gráficos, en orden: `00BFA5`, `0F1B2D`, `7FDFD2`, `6B7785`, `F79009`, `B8C2CC`.

Proporción aproximada: 60–70% blanco o azul noche, 20–30% turquesa y el resto neutros.

## Tipografía

- Por defecto se usa **Arial** en títulos y cuerpo, porque está en todos los PowerPoint y el QA con LibreOffice mide bien los anchos.
- Si Tenpo usa una tipografía corporativa y está instalada en los equipos que abrirán el deck, cámbiala en `BRAND.font.head` (y en `body` si corresponde). Deja algo de holgura en las cajas, porque el QA no la podrá medir bien.

| Elemento | Tamaño |
|---|---|
| Título de portada | 44 pt bold |
| Título de sección | 40 pt bold |
| Título de lámina | 28 pt bold (se reduce solo si no cabe) |
| Kicker | 11 pt bold, mayúsculas, espaciado |
| Cuerpo | 15–16 pt |
| KPI | 34–42 pt bold |
| Fuente / pie | 9 pt |

## Estructura de lámina

- Formato 16:9 ancho (13,33" × 7,5") con márgenes laterales de 0,6".
- Arriba va el kicker opcional y el título de acción. Al pie van la fuente a la izquierda y el wordmark y el número de lámina a la derecha.
- La portada, las secciones y el cierre van en fondo `ink` con círculos `primary`.

## Voz

- Español de Chile, cercano pero profesional. Tenpo es una fintech, así que el tono es moderno y sin formalismos bancarios.
- Los títulos son conclusiones con cifra cuando es posible, como "El GPV interno supera al CMF en $4.396 MM".
- Se evitan anglicismos cuando existe un término claro en español, pero se mantienen los términos de industria (GPV, yield, cash-in).
