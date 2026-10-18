// Monitor Chile: página estática que dibuja los JSON de data/ (generados por app/exportar_monitor.py).
// No calcula indicadores: solo formatea y grafica lo que ya viene calculado.

const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const INTERVALO_REVISION_MS = 5 * 60 * 1000;

const ICONOS = {
  "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.41l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',
  dollar: '<line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  percent: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  briefcase: '<rect width="20" height="14" x="2" y="7" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  sol: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  luna: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
};
const icono = (nombre) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONOS[nombre] || ""}</svg>`;

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// ---------- Formato de números (coma decimal, punto de miles: convención chilena) ----------
const formateadores = {};
function numero(valor, decimales) {
  if (!formateadores[decimales]) {
    formateadores[decimales] = new Intl.NumberFormat("de-DE", { minimumFractionDigits: decimales, maximumFractionDigits: decimales });
  }
  return formateadores[decimales].format(valor);
}

function fmtValor(serie, valor) {
  const redondeado = Number(valor.toFixed(serie.decimales));
  const signo = redondeado < 0 ? "−" : serie.firmado && redondeado > 0 ? "+" : "";
  const txt = signo + numero(Math.abs(redondeado), serie.decimales);
  if (serie.unidad === "%") return txt + "%";
  if (serie.unidad === "CLP") return signo + "$" + numero(Math.abs(redondeado), serie.decimales);
  return txt;
}

function fmtDelta(serie, delta) {
  if (delta === null || delta === undefined) return "";
  const d = serie.delta_tipo === "pp" ? 1 : 2;
  const redondeado = Number(delta.toFixed(d));
  const txt = (redondeado < 0 ? "−" : redondeado > 0 ? "+" : "") + numero(Math.abs(redondeado), d);
  return serie.delta_tipo === "pp" ? `${txt} p.p.` : `${txt}%`;
}

const NOMBRE_TONO = { mejor: "Mejor", peor: "Peor", igual: "Igual" };
const claseTono = (t) => `tono-${t ?? "null"}`;

// ---------- Estado ----------
const estado = { meta: null, indice: null, calendario: null, comentarios: null, graficos: [] };

async function pedirJSON(ruta, version) {
  const resp = await fetch(`data/${ruta}?v=${encodeURIComponent(version || "")}`, { cache: "no-cache" });
  if (!resp.ok) throw new Error(`${ruta}: HTTP ${resp.status}`);
  return resp.json();
}

async function cargarDatos() {
  const meta = await (await fetch(`data/meta.json?t=${Date.now()}`, { cache: "no-store" })).json();
  const v = meta.generado;
  const [indice, calendario, comentarios] = await Promise.all([
    pedirJSON("indice.json", v), pedirJSON("calendario.json", v), pedirJSON("comentarios.json", v),
  ]);
  Object.assign(estado, { meta, indice, calendario, comentarios });
}

// ---------- Gráficos ----------
const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();

function dibujarMini(contenedor, serie) {
  if (!window.echarts) return;
  const grafico = echarts.init(contenedor, null, { renderer: "svg" });
  const datos = serie.mini;
  const valores = datos.map((p) => p[1]);
  const cruzaCero = Math.min(...valores) < 0 && Math.max(...valores) > 0;
  const acento = css("--accent");
  grafico.setOption({
    animation: false,
    grid: { left: 6, right: 8, top: 8, bottom: 4 },
    xAxis: { type: "category", show: false, data: datos.map((p) => p[0]), boundaryGap: false },
    yAxis: { type: "value", show: false, scale: true },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: css("--card-2"), borderColor: css("--border-fuerte"),
      textStyle: { color: css("--text"), fontSize: 12 },
      axisPointer: { type: "line", lineStyle: { color: css("--muted"), type: "dashed" } },
      formatter: (p) => `${etiquetaFecha(p[0].axisValue, serie.frecuencia)}<br><b>${fmtValor(serie, p[0].value)}</b>`,
    },
    series: [{
      type: "line", data: valores, showSymbol: false, symbolSize: 7, lineStyle: { width: 2, color: acento },
      itemStyle: { color: acento },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: acento + "55" }, { offset: 1, color: acento + "00" }]) },
      markPoint: { silent: true, symbol: "circle", symbolSize: 8, itemStyle: { color: acento }, label: { show: false }, data: [{ coord: [datos.length - 1, valores[valores.length - 1]] }] },
      markLine: cruzaCero ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: css("--muted"), type: "dashed", opacity: 0.5 }, data: [{ yAxis: 0 }] } : undefined,
    }],
  });
  const observador = new ResizeObserver(() => grafico.resize());
  observador.observe(contenedor);
  estado.graficos.push({ grafico, observador });
}

function limpiarGraficos() {
  for (const { grafico, observador } of estado.graficos) {
    observador.disconnect();
    grafico.dispose();
  }
  estado.graficos = [];
}

function etiquetaFecha(iso, frecuencia) {
  const [a, m, d] = iso.split("-");
  if (frecuencia === "M") return `${MESES[Number(m) - 1]} ${a}`;
  if (frecuencia === "T") return `T${Math.floor((Number(m) - 1) / 3) + 1} ${a}`;
  return `${d}-${m}-${a}`;
}

// ---------- Piezas de la página ----------
const serieDe = (id) => estado.indice.series.find((s) => s.id === id);

function htmlEncabezado() {
  const tema = document.documentElement.getAttribute("data-theme");
  return `<header class="contenedor encabezado">
    <a class="marca" href="#/">Monitor Chile<small>La economía chilena en datos</small></a>
    <nav class="nav-links" aria-label="Enlaces">
      <a class="opcional" href="../">Reporte completo</a>
      <a class="opcional" href="https://datos-economicos-chile.streamlit.app" target="_blank" rel="noopener">Dashboard interactivo ↗</a>
    </nav>
    <button class="boton-icono" id="cambiar-tema" type="button" aria-label="Cambiar entre tema claro y oscuro" title="Cambiar tema">${icono(tema === "dark" ? "sol" : "luna")}</button>
  </header>`;
}

function htmlPestanas(ruta) {
  const items = [{ id: "", nombre: "Visión general" }, ...estado.indice.temas.map((t) => ({ id: t.id, nombre: t.nombre }))];
  return `<nav class="pestanas" aria-label="Temas">${items
    .map((t) => `<a class="pestana" href="#/${t.id}" ${t.id === ruta ? 'aria-current="page"' : ""}>${esc(t.nombre)}</a>`)
    .join("")}</nav>`;
}

function htmlLinea() {
  const { hoy, eventos } = estado.calendario;
  const textoEstado = { pendiente: "Pendiente", hoy: "Se publica hoy", sin_cargar: "Publicado, cargando…" };
  let divisor = false;
  const piezas = eventos.map((e) => {
    let previo = "";
    if (!divisor && e.fecha > hoy) {
      divisor = true;
      previo = '<li class="divisor-hoy" aria-label="Hoy" id="marca-hoy"></li>';
    }
    const [, m, d] = e.fecha.split("-");
    const serie = e.estado === "cargado" && e.tarjeta ? serieDe(e.tarjeta) : null;
    const dato = serie
      ? `<div class="dato num">${fmtValor(serie, serie.ultimo.valor)}</div><div class="dato-sub">${esc(serie.nombre)} · ${esc(serie.ultimo.etiqueta)}</div>`
      : "";
    const estadoTxt = e.estado === "cargado" && !serie ? "Publicado" : e.estado === "cargado" ? "" : textoEstado[e.estado];
    return `${previo}<li class="evento ${e.estado}">
      <div class="fecha">${Number(d)} ${MESES[Number(m) - 1]}</div>
      <div class="punto"></div>
      <div class="nombre">${esc(e.indicador)}${e.aproximado ? '<span class="aprox" title="Fecha aproximada: el Banco Central no publica una lista fija">aprox.</span>' : ""}</div>
      ${dato}
      ${estadoTxt ? `<div class="estado">${estadoTxt}</div>` : ""}
    </li>`;
  });
  return `<section class="bloque" aria-labelledby="t-linea">
    <div class="bloque-cabecera"><h2 id="t-linea">Últimos datos y lo que viene</h2></div>
    <div class="linea-scroll" id="linea-scroll"><ol class="linea">${piezas.join("")}</ol></div>
    <p class="bloque-nota">Fechas oficiales del INE y del Banco Central (TPM); IMACEC y PIB trimestral son aproximadas.</p>
  </section>`;
}

function htmlTono(serie) {
  if (serie.delta === null) return "";
  const base = serie.previo ? ` vs. ${esc(serie.previo.etiqueta)}` : "";
  const delta = fmtDelta(serie, serie.delta);
  if (!serie.tono) return `<div class="tono"><span class="num">${delta}</span>${base}</div>`;
  return `<div class="tono"><b class="${claseTono(serie.tono)}">${NOMBRE_TONO[serie.tono]}</b> · <span class="num">${delta}</span>${base}</div>`;
}

// Tarjeta grande de la portada: un tema, con su indicador principal y los secundarios en filas.
function htmlTarjetaTema(tema) {
  const s = serieDe(tema.serie);
  const filas = tema.secundarias
    .map((id) => serieDe(id))
    .filter(Boolean)
    .map((x) => {
      const flecha = x.delta === null || Math.abs(x.delta) < 0.05 ? "" : x.delta > 0 ? "▲" : "▼";
      return `<li><span>${esc(x.nombre)}</span><span class="num">${fmtValor(x, x.ultimo.valor)}<span class="flecha ${claseTono(x.tono)}" aria-label="${x.delta > 0 ? "subió" : "bajó"} respecto al período anterior">${flecha}</span></span></li>`;
    })
    .join("");
  return `<article class="tarjeta">
    <h2 class="tarjeta-titulo">${icono(tema.icono)}<a href="#/${tema.id}">${esc(tema.nombre)}</a></h2>
    <div class="indicador">${esc(s.nombre)} · ${esc(s.ultimo.etiqueta)}</div>
    <div class="valor num">${fmtValor(s, s.ultimo.valor)}</div>
    ${htmlTono(s)}
    <div class="mini" data-serie="${esc(s.id)}" role="img" aria-label="Evolución reciente de ${esc(s.nombre)}"></div>
    ${filas ? `<ul class="secundarias">${filas}</ul>` : ""}
    <div class="fuente">Fuente: ${esc(s.fuente)}</div>
  </article>`;
}

// Tarjeta de un indicador, en la página de cada tema.
function htmlTarjetaSerie(s) {
  return `<article class="tarjeta">
    <div class="indicador">${esc(s.nombre)} · ${esc(s.ultimo.etiqueta)}</div>
    <div class="valor num">${fmtValor(s, s.ultimo.valor)}</div>
    ${htmlTono(s)}
    <div class="mini" data-serie="${esc(s.id)}" role="img" aria-label="Evolución reciente de ${esc(s.nombre)}"></div>
    <div class="fuente">Fuente: ${esc(s.fuente)}</div>
  </article>`;
}

function htmlComentarios() {
  if (!estado.comentarios.length) return "";
  return `<section class="bloque comentarios" aria-labelledby="t-coment">
    <h2 id="t-coment">Lo último, comentado</h2>
    ${estado.comentarios.map((c) => `<p><strong>${esc(c.titulo)}</strong>: ${esc(c.texto)}</p>`).join("")}
    <p class="bloque-nota">Comentario generado automáticamente con plantillas de texto (no con un modelo de lenguaje) a partir de los mismos datos de las tarjetas.</p>
  </section>`;
}

function htmlPie() {
  const g = new Date(estado.meta.generado);
  const hora = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(g);
  return `<footer class="contenedor pie">
    Datos: Banco Central de Chile, INE, Yahoo Finance. Actualizado ${esc(hora)} (hora de Chile); la página se refresca sola cuando hay datos nuevos.<br>
    «Mejor» y «peor» comparan contra el período anterior según si que el indicador suba es bueno o malo para la economía; el dólar, la bolsa y la TPM no llevan juicio.
    Es información de referencia, no una recomendación de inversión. <a href="../">Reporte completo</a> · <a href="https://datos-economicos-chile.streamlit.app" target="_blank" rel="noopener">Dashboard interactivo</a>
  </footer>`;
}

// ---------- Render ----------
function rutaActual() {
  const r = location.hash.replace(/^#\/?/, "");
  return estado.indice.temas.some((t) => t.id === r) ? r : "";
}

function render() {
  limpiarGraficos();
  const ruta = rutaActual();
  let cuerpo;
  if (ruta === "") {
    cuerpo = `${htmlLinea()}<div class="rejilla">${estado.indice.temas.map(htmlTarjetaTema).join("")}</div>${htmlComentarios()}`;
  } else {
    const series = estado.indice.series.filter((s) => s.tema === ruta);
    cuerpo = `<div class="rejilla">${series.map(htmlTarjetaSerie).join("")}</div>`;
  }
  document.getElementById("app").innerHTML = `${htmlEncabezado()}
    <main class="contenedor" id="contenido">${htmlPestanas(ruta)}${cuerpo}</main>${htmlPie()}`;

  document.querySelectorAll(".mini").forEach((el) => dibujarMini(el, serieDe(el.dataset.serie)));
  document.getElementById("cambiar-tema").addEventListener("click", cambiarTema);
  const marca = document.getElementById("marca-hoy"), scroll = document.getElementById("linea-scroll");
  if (marca && scroll) scroll.scrollLeft = Math.max(0, marca.offsetLeft - 2 * 168);
}

function cambiarTema() {
  const nuevo = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", nuevo);
  try { localStorage.setItem("monitor-tema", nuevo); } catch (e) { /* sin almacenamiento: el cambio vale solo para esta visita */ }
  document.querySelector('meta[name="theme-color"]').setAttribute("content", nuevo === "dark" ? "#0b0d12" : "#f4f5f9");
  render();
}

// Si el pipeline publicó datos nuevos mientras la página estaba abierta, se recargan sin perder la pestaña.
async function revisarDatosNuevos() {
  try {
    const meta = await (await fetch(`data/meta.json?t=${Date.now()}`, { cache: "no-store" })).json();
    if (meta.generado !== estado.meta.generado) {
      await cargarDatos();
      render();
    }
  } catch (e) { /* sin conexión: se reintenta en el próximo ciclo */ }
}

async function iniciar() {
  try {
    await cargarDatos();
  } catch (e) {
    document.getElementById("app").innerHTML = `<p class="error">No se pudieron cargar los datos (${esc(e.message)}). Intenta recargar la página.</p>`;
    return;
  }
  render();
  window.addEventListener("hashchange", () => { render(); window.scrollTo({ top: 0 }); });
  setInterval(revisarDatosNuevos, INTERVALO_REVISION_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) revisarDatosNuevos(); });
}

iniciar();
