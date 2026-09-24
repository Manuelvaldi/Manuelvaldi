// Deck de ejemplo que usa todos los layouts. Sirve de plantilla para copiar.
// node example_deck.js [salida.pptx]
const T = require("./tenpo.js");

(async () => {
  const out = process.argv[2] || "ejemplo_tenpo.pptx";
  const deck = T.createDeck({ title: "Neobanca Lending Overview — Chile" });

  T.cover(deck, {
    title: "Neobanca Lending Overview",
    subtitle: "Tarjeta de Crédito Chile: tamaño de mercado, cartera y rentabilidad",
    area: "Finanzas · Data",
    date: "Septiembre 2026",
  });

  T.agenda(deck, { items: ["Mercado", "Cartera Tarjeta de Crédito", "GPV interno vs CMF", "Próximos pasos"] });

  T.section(deck, { number: 1, title: "Mercado", subtitle: "Chile: población, inclusión financiera y elegibilidad" });

  T.kpis(deck, {
    kicker: "Mercado Chile",
    title: "La mitad de los adultos está bancarizada y 9,2 MM son elegibles para crédito",
    items: [
      { value: "16,6 MM", label: "Población adulta / económicamente activa" },
      { value: "51,1%", label: "Incluidos financieramente (en bureau)" },
      { value: "9,17 MM", label: "Elegibles a crédito Neobanca" },
      { value: "2,8%", label: "Clientes con crédito vigente sobre elegibles", delta: "Espacio para crecer" },
    ],
    source: "Equifax, INE; Neobanca Lending Overview",
  });

  T.chart(deck, {
    kicker: "Cartera TC",
    title: "La cartera de Tarjeta de Crédito alcanza US$156,5 MM",
    type: "col",
    series: [{ name: "Cartera (US$ MM)", labels: ["Mar-26", "Abr-26", "May-26", "Jun-26", "Jul-26", "Ago-26"], values: [118.2, 125.9, 133.4, 141.0, 148.7, 156.5] }],
    numFmt: "#,##0.0",
    takeaways: ["Crecimiento mensual promedio de ~5,8%", "360,6 mil créditos únicos", "Yield anualizado de 21,6% sobre saldo"],
    source: "Neobanca Lending Overview_vTenpo (cifras mensuales ilustrativas)",
  });

  T.table(deck, {
    kicker: "Rentabilidad por producto",
    title: "Chile TC es el único producto con métricas completas; el resto está pendiente",
    header: ["Producto", "Cartera (US$ MM)", "Créditos (miles)", "Yield", "Costo de fondos", "Contribución neta"],
    rows: [
      ["Chile Tarjeta de Crédito", "156,5", "360,6", "21,6%", "pend.", "pend."],
      ["Perú Term Loan Personas", "—", "—", "—", "—", "—"],
      ["Perú Term Loan MyPE", "—", "—", "—", "—", "—"],
      ["Perú Tarjeta de Crédito", "—", "—", "—", "—", "—"],
      ["Bolivia Term Loan", "—", "—", "—", "—", "—"],
    ],
    highlightRow: 0,
    colW: [3.6, 1.65, 1.65, 1.3, 1.9, 2.03],
    source: "Neobanca Lending Overview_vTenpo",
  });

  T.twoColumn(deck, {
    kicker: "Conciliación",
    title: "El GPV interno supera al CMF en $4.396 MM por diferencias de definición",
    left: { heading: "GPV interno", bullets: ["Incluye compras y pago de servicios (MCC 4900, 4814)", "Fecha de liquidación Mastercard", "Considera cuentas activas y cerradas"] },
    right: { heading: "Publicación CMF", bullets: ["Solo compras", "Mes calendario de procesamiento", "Excluye tarjetas cerradas y legadas"] },
    source: "Cuadro Comparativo GPV vs CMF, febrero 2026",
  });

  T.content(deck, {
    kicker: "Implicancia",
    title: "Hay que reportar ambas cifras y explicar la brecha",
    bullets: [
      "Usar GPV interno para gestión y metas comerciales",
      "Usar la cifra CMF para comparar con la industria",
      "Agregar una nota de conciliación mensual al reporte de directorio",
    ],
    highlight: { value: "6,5%", text: "brecha de la Tarjeta Prepago en febrero 2026 ($67.512 MM vs $63.116 MM)" },
    source: "Cuadro Comparativo GPV vs CMF",
  });

  T.steps(deck, {
    title: "Plan de cierre de métricas pendientes",
    items: [
      { title: "Costo de fondos", text: "Tesorería entrega la curva por producto" },
      { title: "Gasto de crédito", text: "Riesgo calcula provisiones anualizadas" },
      { title: "Contribución neta", text: "Finanzas consolida el P&L por producto" },
      { title: "Revisión", text: "Validación con gerencia antes del directorio" },
    ],
  });

  T.closing(deck, {
    items: ["Completar métricas pendientes de Chile TC", "Levantar datos de Perú y Bolivia", "Presentar al directorio en octubre"],
    contact: "Equipo de Finanzas · Tenpo",
  });

  await deck.save(out);
  console.log("OK", out);
})();
