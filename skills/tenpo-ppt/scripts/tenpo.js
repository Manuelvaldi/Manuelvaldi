// tenpo.js — layouts de marca Tenpo para pptxgenjs.
//
// Uso:
//   const T = require("<skill>/scripts/tenpo.js");
//   const deck = T.createDeck({ title: "Resultados Q3" });
//   T.cover(deck, { title: "...", subtitle: "...", date: "Septiembre 2026" });
//   T.kpis(deck, { title: "...", items: [{ value: "$156,5 MM", label: "Cartera TC" }] });
//   await deck.save("salida.pptx");
//
// Todos los colores y tipografías viven en BRAND. Si llega el manual de marca
// oficial, se cambian solo ahí (y en references/brand.md).

const path = require("path");
const fs = require("fs");

let pptxgen;
try {
  pptxgen = require("pptxgenjs");
} catch (e) {
  pptxgen = require(require.resolve("pptxgenjs", { paths: [process.cwd()] }));
}

// ---------------------------------------------------------------------------
// Tokens de marca (hex sin "#", pptxgenjs se corrompe con "#")
// ---------------------------------------------------------------------------
const BRAND = {
  color: {
    primary: "00BFA5", // turquesa Tenpo — color dominante de acento
    primaryDark: "00897B", // turquesa oscuro: texto de acento sobre blanco
    primaryLight: "E0F7F4", // tinte turquesa: fondos de tarjetas
    ink: "0F1B2D", // azul noche: fondos oscuros y títulos
    text: "1F2933", // texto principal sobre claro
    muted: "6B7785", // captions, fuentes, ejes
    line: "D9DEE3", // bordes y grillas sutiles
    bg: "FFFFFF",
    bgSoft: "F4F6F8", // fondo de tarjetas neutras
    positive: "12B76A",
    negative: "F04438",
    warning: "F79009",
    white: "FFFFFF",
  },
  // Serie de colores para gráficos, en orden de uso
  chart: ["00BFA5", "0F1B2D", "7FDFD2", "6B7785", "F79009", "B8C2CC"],
  font: {
    head: "Arial", // cambiar por la tipografía oficial si se tiene instalada
    body: "Arial",
  },
  wordmark: "tenpo",
};

const W = 13.333; // LAYOUT_WIDE
const H = 7.5;
const M = 0.6; // margen lateral

// ---------------------------------------------------------------------------
// Formato de números (Chile: punto de miles, coma decimal)
// ---------------------------------------------------------------------------
function num(n, dec = 0) {
  return Number(n).toLocaleString("es-CL", {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  });
}
const fmt = {
  num,
  pct: (n, dec = 1) => `${num(n * 100, dec)}%`, // 0.216 -> "21,6%"
  pp: (n, dec = 1) => `${n >= 0 ? "+" : ""}${num(n, dec)} pp`,
  clpMM: (n, dec = 0) => `$${num(n / 1e6, dec)} MM`, // pesos -> millones
  usdMM: (n, dec = 1) => `US$${num(n / 1e6, dec)} MM`,
  delta: (n, dec = 1) => `${n >= 0 ? "▲" : "▼"} ${num(Math.abs(n) * 100, dec)}%`,
};

// ---------------------------------------------------------------------------
// Deck
// ---------------------------------------------------------------------------
function createDeck({ title = "Presentación Tenpo", author = "Tenpo", logo } = {}) {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.title = title;
  pres.author = author;
  pres.company = "Tenpo";
  pres.theme = { headFontFace: BRAND.font.head, bodyFontFace: BRAND.font.body };

  const defaultLogo = path.join(__dirname, "..", "assets", "logo.png");
  const defaultLogoDark = path.join(__dirname, "..", "assets", "logo-white.png");
  const deck = {
    pres,
    count: 0,
    logo: logo || (fs.existsSync(defaultLogo) ? defaultLogo : null),
    logoDark: fs.existsSync(defaultLogoDark) ? defaultLogoDark : null,
    save: (file) => pres.writeFile({ fileName: file }),
  };
  return deck;
}

function newSlide(deck, { dark = false } = {}) {
  const s = deck.pres.addSlide();
  s.background = { color: dark ? BRAND.color.ink : BRAND.color.bg };
  deck.count += 1;
  return s;
}

function text(slide, str, opts) {
  slide.addText(str, {
    isTextBox: true,
    fontFace: BRAND.font.body,
    color: BRAND.color.text,
    margin: 0,
    valign: "top",
    ...opts,
  });
}

// Wordmark: usa assets/logo.png si existe; si no, "tenpo" en texto
function wordmark(deck, slide, { x, y, h = 0.35, dark = false, size = 20 }) {
  const img = dark ? deck.logoDark || null : deck.logo;
  if (img) {
    slide.addImage({ path: img, x, y, h, w: h * 3.2, sizing: { type: "contain", w: h * 3.2, h } });
  } else {
    text(slide, BRAND.wordmark, {
      x, y, w: 2, h,
      fontFace: BRAND.font.head, fontSize: size, bold: true,
      color: dark ? BRAND.color.primary : BRAND.color.primaryDark,
      valign: "middle",
    });
  }
}

function footer(deck, slide, { source, dark = false } = {}) {
  const c = dark ? "9AA5B1" : BRAND.color.muted;
  if (source) {
    text(slide, `Fuente: ${source}`, { x: M, y: H - 0.45, w: 9, h: 0.25, fontSize: 9, color: c, valign: "middle" });
  }
  text(slide, String(deck.count), { x: W - M - 0.5, y: H - 0.45, w: 0.5, h: 0.25, fontSize: 9, color: c, align: "right", valign: "middle" });
  wordmark(deck, slide, { x: W - M - 1.6, y: H - 0.5, h: 0.3, dark, size: 12 });
}

// Título de acción (la conclusión) + kicker opcional sobre el título
function header(slide, { title, kicker, dark = false }) {
  let y = 0.45;
  if (kicker) {
    text(slide, kicker.toUpperCase(), {
      x: M, y, w: W - 2 * M, h: 0.3,
      fontSize: 11, bold: true, charSpacing: 2,
      color: dark ? BRAND.color.primary : BRAND.color.primaryDark,
    });
    y += 0.35;
  }
  text(slide, title, {
    x: M, y, w: W - 2 * M, h: 0.9,
    fontFace: BRAND.font.head, fontSize: 28, bold: true,
    color: dark ? BRAND.color.white : BRAND.color.ink,
    fit: "shrink",
  });
  return y + 1.05; // y donde empieza el contenido
}

// ---------------------------------------------------------------------------
// Layouts
// ---------------------------------------------------------------------------

// Portada: fondo azul noche, círculo turquesa como motivo
function cover(deck, { title, subtitle, date, area, notes }) {
  const s = newSlide(deck, { dark: true });
  s.addShape(deck.pres.shapes.OVAL, { x: 8.9, y: -1.6, w: 6.5, h: 6.5, fill: { color: BRAND.color.primary } });
  s.addShape(deck.pres.shapes.OVAL, { x: 10.6, y: 4.3, w: 3.2, h: 3.2, fill: { color: BRAND.color.primary, transparency: 70 } });
  wordmark(deck, s, { x: M, y: 0.6, h: 0.5, dark: true, size: 28 });
  text(s, title, {
    x: M, y: 2.4, w: 8, h: 1.8,
    fontFace: BRAND.font.head, fontSize: 44, bold: true, color: BRAND.color.white, valign: "bottom", fit: "shrink",
  });
  if (subtitle) text(s, subtitle, { x: M, y: 4.35, w: 7.8, h: 0.9, fontSize: 18, color: "C9D2DB" });
  const meta = [area, date].filter(Boolean).join("  ·  ");
  if (meta) text(s, meta, { x: M, y: H - 1.0, w: 7, h: 0.35, fontSize: 12, color: BRAND.color.primary, bold: true });
  if (notes) s.addNotes(notes);
  return s;
}

// Agenda: lista numerada con números turquesa grandes
function agenda(deck, { title = "Agenda", items, notes }) {
  const s = newSlide(deck);
  const y0 = header(s, { title });
  const n = items.length;
  const rowH = Math.min(0.85, (H - y0 - 0.9) / n);
  items.forEach((it, i) => {
    const y = y0 + i * rowH;
    s.addShape(deck.pres.shapes.OVAL, { x: M, y: y + 0.08, w: 0.5, h: 0.5, fill: { color: BRAND.color.primary } });
    text(s, String(i + 1), { x: M, y: y + 0.08, w: 0.5, h: 0.5, fontSize: 16, bold: true, color: BRAND.color.white, align: "center", valign: "middle" });
    text(s, it, { x: M + 0.75, y: y + 0.08, w: W - 2 * M - 1, h: 0.5, fontSize: 18, valign: "middle" });
  });
  footer(deck, s);
  if (notes) s.addNotes(notes);
  return s;
}

// Separador de sección
function section(deck, { number, title, subtitle, notes }) {
  const s = newSlide(deck, { dark: true });
  s.addShape(deck.pres.shapes.OVAL, { x: -1.5, y: 3.8, w: 5, h: 5, fill: { color: BRAND.color.primary, transparency: 80 } });
  if (number != null) {
    text(s, String(number).padStart(2, "0"), { x: M, y: 1.6, w: 3, h: 1.4, fontFace: BRAND.font.head, fontSize: 80, bold: true, color: BRAND.color.primary });
  }
  text(s, title, { x: M, y: 3.1, w: W - 2 * M, h: 1.1, fontFace: BRAND.font.head, fontSize: 40, bold: true, color: BRAND.color.white, fit: "shrink" });
  if (subtitle) text(s, subtitle, { x: M, y: 4.25, w: 9, h: 0.8, fontSize: 18, color: "C9D2DB" });
  footer(deck, s, { dark: true });
  if (notes) s.addNotes(notes);
  return s;
}

// Texto + tarjeta de mensaje clave a la derecha
function content(deck, { title, kicker, bullets = [], highlight, source, notes }) {
  const s = newSlide(deck);
  const y0 = header(s, { title, kicker });
  const hasSide = Boolean(highlight);
  const wL = hasSide ? 7.4 : W - 2 * M;
  s.addText(
    bullets.map((b, i) => ({
      text: b,
      options: { bullet: { indent: 18 }, breakLine: i < bullets.length - 1, paraSpaceAfter: 10 },
    })),
    { isTextBox: true, x: M, y: y0, w: wL, h: H - y0 - 0.9, fontFace: BRAND.font.body, fontSize: 16, color: BRAND.color.text, valign: "top", margin: 0 }
  );
  if (hasSide) {
    const x = M + wL + 0.5;
    const w = W - M - x;
    s.addShape(deck.pres.shapes.ROUNDED_RECTANGLE, { x, y: y0, w, h: 3.6, fill: { color: BRAND.color.primaryLight }, rectRadius: 0.15 });
    if (highlight.value) {
      text(s, highlight.value, { x: x + 0.35, y: y0 + 0.35, w: w - 0.7, h: 1.1, fontFace: BRAND.font.head, fontSize: 40, bold: true, color: BRAND.color.primaryDark, fit: "shrink" });
    }
    text(s, highlight.text, { x: x + 0.35, y: y0 + (highlight.value ? 1.5 : 0.35), w: w - 0.7, h: 1.9, fontSize: 15, color: BRAND.color.ink });
  }
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// KPIs: 2 a 4 tarjetas con número grande, etiqueta y variación
function kpis(deck, { title, kicker, items, source, notes }) {
  const s = newSlide(deck);
  const y0 = header(s, { title, kicker }) + 0.2;
  const n = items.length;
  const gap = 0.35;
  const w = (W - 2 * M - gap * (n - 1)) / n;
  const h = 2.9;
  items.forEach((k, i) => {
    const x = M + i * (w + gap);
    const lead = i === 0;
    s.addShape(deck.pres.shapes.ROUNDED_RECTANGLE, {
      x, y: y0, w, h, rectRadius: 0.15,
      fill: { color: lead ? BRAND.color.ink : BRAND.color.bgSoft },
    });
    text(s, k.value, {
      x: x + 0.3, y: y0 + 0.4, w: w - 0.6, h: 1.1,
      fontFace: BRAND.font.head, fontSize: n > 3 ? 34 : 42, bold: true,
      color: lead ? BRAND.color.primary : BRAND.color.ink, fit: "shrink",
    });
    text(s, k.label, { x: x + 0.3, y: y0 + 1.55, w: w - 0.6, h: 0.7, fontSize: 14, color: lead ? "C9D2DB" : BRAND.color.muted });
    if (k.delta != null) {
      const neg = String(k.delta).trim().startsWith("▼") || String(k.delta).trim().startsWith("-");
      const good = k.good != null ? k.good : !neg;
      text(s, String(k.delta), {
        x: x + 0.3, y: y0 + 2.2, w: w - 0.6, h: 0.4, fontSize: 13, bold: true,
        color: good ? BRAND.color.positive : BRAND.color.negative,
      });
    }
  });
  if (items.some((k) => k.note)) {
    text(s, items.filter((k) => k.note).map((k) => k.note).join("  ·  "), { x: M, y: y0 + h + 0.3, w: W - 2 * M, h: 0.5, fontSize: 12, color: BRAND.color.muted });
  }
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// Gráfico nativo + panel de conclusiones a la derecha
// type: "bar" | "col" | "line" | "pie" | "doughnut" | "area"
// series: [{ name, labels: [...], values: [...] }]
function chart(deck, { title, kicker, type = "col", series, takeaways = [], source, notes, stacked = false, numFmt, valueLabels = true }) {
  const s = newSlide(deck);
  const y0 = header(s, { title, kicker });
  const hasSide = takeaways.length > 0;
  const wC = hasSide ? 8.3 : W - 2 * M;
  const h = H - y0 - 0.8;

  const t = { bar: "bar", col: "bar", line: "line", pie: "pie", doughnut: "doughnut", area: "area" }[type];
  const round = t === "pie" || t === "doughnut";
  const opts = {
    x: M, y: y0, w: wC, h,
    chartColors: round ? BRAND.chart : BRAND.chart.slice(0, series.length),
    fontFace: BRAND.font.body,
    catAxisLabelColor: BRAND.color.muted, valAxisLabelColor: BRAND.color.muted,
    catAxisLabelFontSize: 11, valAxisLabelFontSize: 10,
    valGridLine: { color: BRAND.color.line, size: 0.5 }, catGridLine: { style: "none" },
    catAxisLineShow: false, valAxisLineShow: false,
    showLegend: series.length > 1 || round, legendPos: "b", legendFontSize: 11, legendColor: BRAND.color.text,
    showValue: valueLabels, dataLabelFontSize: 10, dataLabelColor: BRAND.color.text,
  };
  if (t === "bar") {
    opts.barDir = type === "bar" ? "bar" : "col";
    opts.barGapWidthPct = 60;
    if (stacked) { opts.barGrouping = "stacked"; opts.dataLabelPosition = "ctr"; opts.dataLabelColor = BRAND.color.white; }
    else opts.dataLabelPosition = "outEnd";
  }
  if (t === "line") { opts.lineSize = 2.5; opts.lineDataSymbol = "circle"; opts.lineDataSymbolSize = 7; opts.dataLabelPosition = "t"; }
  if (round) { opts.showPercent = true; opts.showValue = false; opts.dataLabelColor = BRAND.color.white; opts.holeSize = 60; }
  if (numFmt) { opts.dataLabelFormatCode = numFmt; opts.valAxisLabelFormatCode = numFmt; }
  s.addChart(deck.pres.charts[t.toUpperCase()], series, opts);

  if (hasSide) {
    const x = M + wC + 0.4;
    const w = W - M - x;
    text(s, "CONCLUSIONES", { x, y: y0, w, h: 0.3, fontSize: 11, bold: true, charSpacing: 2, color: BRAND.color.primaryDark });
    s.addText(
      takeaways.map((b, i) => ({ text: b, options: { bullet: { indent: 14 }, breakLine: i < takeaways.length - 1, paraSpaceAfter: 12 } })),
      { isTextBox: true, x, y: y0 + 0.45, w, h: h - 0.45, fontFace: BRAND.font.body, fontSize: 14, color: BRAND.color.text, valign: "top", margin: 0 }
    );
  }
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// Tabla: header azul noche, filas cebra suaves, números alineados a la derecha
// rows: array de arrays (strings ya formateados). highlightRow: índice a destacar.
function table(deck, { title, kicker, header: head, rows, source, notes, colW, highlightRow }) {
  const s = newSlide(deck);
  const y0 = header(s, { title, kicker });
  const isNum = (v) => /^[\s$US▲▼+\-−(]*[\d.,]+\s*(%|pp|MM|x)?\)?$/.test(String(v).trim());
  const cell = (v, r) => ({
    text: String(v),
    options: {
      fontSize: rows.length > 10 ? 11 : 13,
      color: r === highlightRow ? BRAND.color.ink : BRAND.color.text,
      bold: r === highlightRow,
      fill: { color: r === highlightRow ? BRAND.color.primaryLight : r % 2 ? BRAND.color.bgSoft : BRAND.color.white },
      align: isNum(v) ? "right" : "left",
    },
  });
  const data = [
    head.map((h, i) => ({ text: h, options: { bold: true, color: BRAND.color.white, fill: { color: BRAND.color.ink }, fontSize: 12, align: i === 0 ? "left" : "right" } })),
    ...rows.map((r, ri) => r.map((v) => cell(v, ri))),
  ];
  s.addTable(data, {
    x: M, y: y0, w: W - 2 * M, colW,
    fontFace: BRAND.font.body, border: { type: "solid", pt: 0.5, color: BRAND.color.line },
    rowH: 0.4, margin: [0.05, 0.12, 0.05, 0.12], valign: "middle", autoPage: false,
  });
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// Dos columnas comparativas (ej. antes/después, GPV interno vs CMF)
function twoColumn(deck, { title, kicker, left, right, source, notes }) {
  const s = newSlide(deck);
  const y0 = header(s, { title, kicker });
  const gap = 0.4;
  const w = (W - 2 * M - gap) / 2;
  const maxN = Math.max(left.bullets.length, right.bullets.length);
  const h = Math.min(H - y0 - 0.9, 1.5 + maxN * 0.62);
  [left, right].forEach((col, i) => {
    const x = M + i * (w + gap);
    const accent = i === 1;
    s.addShape(deck.pres.shapes.ROUNDED_RECTANGLE, { x, y: y0, w, h, rectRadius: 0.15, fill: { color: accent ? BRAND.color.primaryLight : BRAND.color.bgSoft } });
    text(s, col.heading, { x: x + 0.35, y: y0 + 0.3, w: w - 0.7, h: 0.5, fontFace: BRAND.font.head, fontSize: 20, bold: true, color: accent ? BRAND.color.primaryDark : BRAND.color.ink });
    s.addText(
      col.bullets.map((b, j) => ({ text: b, options: { bullet: { indent: 16 }, breakLine: j < col.bullets.length - 1, paraSpaceAfter: 8 } })),
      { isTextBox: true, x: x + 0.35, y: y0 + 0.95, w: w - 0.7, h: h - 1.2, fontFace: BRAND.font.body, fontSize: 15, color: BRAND.color.text, valign: "top", margin: 0 }
    );
  });
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// Proceso / timeline horizontal de 3 a 6 pasos
function steps(deck, { title, kicker, items, source, notes }) {
  const s = newSlide(deck);
  const y0 = Math.max(header(s, { title, kicker }) + 0.3, 2.4);
  const n = items.length;
  const gap = 0.3;
  const w = (W - 2 * M - gap * (n - 1)) / n;
  s.addShape(deck.pres.shapes.LINE, { x: M + w / 2, y: y0 + 0.35, w: W - 2 * M - w, h: 0, line: { color: BRAND.color.line, width: 2 } });
  items.forEach((it, i) => {
    const x = M + i * (w + gap);
    s.addShape(deck.pres.shapes.OVAL, { x: x + w / 2 - 0.35, y: y0, w: 0.7, h: 0.7, fill: { color: i === 0 ? BRAND.color.ink : BRAND.color.primary } });
    text(s, String(i + 1), { x: x + w / 2 - 0.35, y: y0, w: 0.7, h: 0.7, fontSize: 18, bold: true, color: BRAND.color.white, align: "center", valign: "middle" });
    text(s, it.title, { x, y: y0 + 0.95, w, h: 0.6, fontFace: BRAND.font.head, fontSize: 16, bold: true, color: BRAND.color.ink, align: "center" });
    if (it.text) text(s, it.text, { x, y: y0 + 1.55, w, h: 2.2, fontSize: 13, color: BRAND.color.muted, align: "center" });
  });
  footer(deck, s, { source });
  if (notes) s.addNotes(notes);
  return s;
}

// Cierre: próximos pasos o mensaje final
function closing(deck, { title = "Próximos pasos", items = [], contact, notes }) {
  const s = newSlide(deck, { dark: true });
  s.addShape(deck.pres.shapes.OVAL, { x: 9.8, y: 2.2, w: 6, h: 6, fill: { color: BRAND.color.primary } });
  text(s, title, { x: M, y: 0.9, w: 8.5, h: 1, fontFace: BRAND.font.head, fontSize: 36, bold: true, color: BRAND.color.white });
  items.forEach((it, i) => {
    const y = 2.2 + i * 0.85;
    text(s, String(i + 1).padStart(2, "0"), { x: M, y, w: 0.8, h: 0.6, fontSize: 22, bold: true, color: BRAND.color.primary, valign: "middle" });
    text(s, it, { x: M + 0.9, y, w: 7.8, h: 0.6, fontSize: 17, color: BRAND.color.white, valign: "middle", fit: "shrink" });
  });
  if (contact) text(s, contact, { x: M, y: H - 1.0, w: 8, h: 0.35, fontSize: 12, color: "C9D2DB" });
  wordmark(deck, s, { x: M, y: H - 0.55, h: 0.3, dark: true, size: 14 });
  if (notes) s.addNotes(notes);
  return s;
}

module.exports = {
  BRAND, W, H, M, fmt,
  createDeck, newSlide, text, header, footer, wordmark,
  cover, agenda, section, content, kpis, chart, table, twoColumn, steps, closing,
};
