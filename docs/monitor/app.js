// Monitor Chile: página estática que dibuja los JSON de data/ (generados por app/exportar_monitor.py).
// No calcula indicadores: solo formatea y grafica lo que ya viene calculado.

const VISTAS = [["ultimo", "Último dato"], ["ytd", "En lo que va del año"], ["12m", "Últimos 12 meses"]];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const INTERVALO_REVISION_MS = 5 * 60 * 1000;

const ICONOS = {
  "trending-up": '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/>',
  tag: '<path d="M12.59 2.59A2 2 0 0 0 11.17 2H4a2 2 0 0 0-2 2v7.17a2 2 0 0 0 .59 1.41l8.7 8.7a2.43 2.43 0 0 0 3.42 0l6.58-6.58a2.43 2.43 0 0 0 0-3.42z"/><circle cx="7.5" cy="7.5" r=".5" fill="currentColor"/>',
  dollar: '<line x1="12" y1="2" x2="12" y2="22"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>',
  percent: '<line x1="19" y1="5" x2="5" y2="19"/><circle cx="6.5" cy="6.5" r="2.5"/><circle cx="17.5" cy="17.5" r="2.5"/>',
  briefcase: '<rect width="20" height="14" x="2" y="7" rx="2"/><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>',
  globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
  flag: '<path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z"/><line x1="4" y1="22" x2="4" y2="15"/>',
  scale: '<path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/><path d="M7 21h10"/><path d="M12 3v18"/><path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>',
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
  const abs = numero(Math.abs(redondeado), serie.decimales);
  if (serie.unidad === "%") return `${signo}${abs}%`;
  if (serie.unidad === "pp") return `${signo}${abs} p.p.`;
  if (serie.unidad === "CLP") return `${signo}$${abs}`;
  return `${signo}${serie.prefijo || ""}${abs}${serie.sufijo || ""}`;
}

// Formato para gráficos compuestos (llevan `unidad` y `decimales`, sin prefijo/sufijo propios).
function fmtGen(g, v) {
  if (v === null || v === undefined) return "";
  const dec = g.decimales ?? 1, abs = numero(Math.abs(v), dec), signo = v < 0 ? "−" : "";
  if (g.unidad === "%") return `${signo}${abs}%`;
  if (g.unidad === "pp") return `${signo}${abs} p.p.`;
  if (g.unidad === "US$") return `${signo}US$${abs}`;
  if (g.unidad === "US$ MM") return `${signo}US$${abs} MM`;
  return `${signo}${abs}`;
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
const estado = { meta: null, indice: null, calendario: null, comentarios: null, graficos: [], detalles: {}, compuestos: {}, revisiones: null, renderId: 0, vista: "ultimo" };

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
  Object.assign(estado, { meta, indice, calendario, comentarios, detalles: {}, compuestos: {}, revisiones: null });
}

async function cargarDetalle(id) {
  if (!estado.detalles[id]) estado.detalles[id] = await pedirJSON(`series/${id}.json`, estado.meta.generado);
  return estado.detalles[id];
}

async function cargarCompuesto(id) {
  if (!estado.compuestos[id]) estado.compuestos[id] = await pedirJSON(`graficos/${id}.json`, estado.meta.generado);
  return estado.compuestos[id];
}

async function cargarRevisiones() {
  if (!estado.revisiones) estado.revisiones = await pedirJSON("revisiones.json", estado.meta.generado);
  return estado.revisiones;
}

// ---------- Gráficos ----------
const css = (nombre) => getComputedStyle(document.documentElement).getPropertyValue(nombre).trim();

function dibujarMini(contenedor, serie) {
  if (!window.echarts) return;
  const grafico = echarts.init(contenedor, null, { renderer: "svg" });
  const datos = serie.mini;
  const valores = datos.map((p) => p[1]);
  const numericos = valores.filter((v) => v !== null);
  const cruzaCero = Math.min(...numericos) < 0 && Math.max(...numericos) > 0;
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
      formatter: (p) => (p[0].value === null || p[0].value === undefined ? "" : `${etiquetaFecha(p[0].axisValue, serie.frecuencia)}<br><b>${fmtValor(serie, p[0].value)}</b>`),
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
  if (frecuencia === "A") return a;
  return `${d}-${m}-${a}`;
}

// ---------- Estado de los datos y búsqueda ----------
const norm = (t) => String(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const diasDesde = (iso) => Math.floor((Date.now() - new Date(iso + "T00:00:00Z").getTime()) / 86400000);

// Las series de las vistas "en el año" / "12 meses" se calculan de otras: contarlas aparte duplicaría los avisos.
function idsDerivados() {
  const base = new Set([...estado.indice.temas.flatMap((t) => [t.serie, ...t.secundarias]), ...estado.indice.series.map((x) => x.id).filter((id) => !estado.indice.temas.some((t) => Object.values(t.vistas || {}).includes(id)))]);
  return new Set(estado.indice.temas.flatMap((t) => Object.values(t.vistas || {})).filter((id) => !base.has(id)));
}
const seriesBase = () => { const d = idsDerivados(); return estado.indice.series.filter((s) => !d.has(s.id)); };
const seriesDemoradas = () => seriesBase().filter((s) => s.alerta !== false && diasDesde(s.ultimo.fecha) > s.max_dias);
const horasDesdeGenerado = () => (Date.now() - new Date(estado.meta.generado).getTime()) / 3600000;
const pipelineAtrasado = () => horasDesdeGenerado() > 72;

const todasLasPestanas = () => [...estado.indice.temas, ...(estado.indice.secciones || [])];

function buscar(texto) {
  const tokens = norm(texto).split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const nombrePestana = Object.fromEntries(todasLasPestanas().map((t) => [t.id, t.nombre]));
  const candidatos = [
    ...estado.indice.series.map((s) => ({
      titulo: s.nombre, sub: nombrePestana[s.tema] || "", valor: fmtValor(s, s.ultimo.valor), hash: `#/serie/${s.id}`,
      pajar: `${norm(s.nombre)} ${norm(nombrePestana[s.tema] || "")} ${norm(s.fuente)} ${norm(s.definicion || "")}`,
    })),
    ...(estado.indice.graficos || []).map((g) => ({
      titulo: g.nombre, sub: `${nombrePestana[g.pestana] || ""} · gráfico`, valor: "", hash: `#/${g.pestana}/${g.id}`,
      pajar: `${norm(g.nombre)} ${norm(nombrePestana[g.pestana] || "")} ${norm(g.definicion || "")}`,
    })),
    ...todasLasPestanas().map((t) => ({ titulo: t.nombre, sub: "Sección", valor: "", hash: `#/${t.id}`, pajar: `${norm(t.nombre)} ${norm(t.intro || "")}` })),
  ];
  return candidatos
    .filter((c) => tokens.every((t) => c.pajar.includes(t)))
    .map((c) => ({ ...c, puntaje: tokens.every((t) => norm(c.titulo).includes(t)) ? 0 : 1 }))
    .sort((a, b) => a.puntaje - b.puntaje)
    .slice(0, 10);
}

function activarBuscador() {
  const entrada = document.getElementById("buscar"), lista = document.getElementById("resultados");
  if (!entrada) return;
  let items = [], activo = -1;
  const cerrar = () => { lista.hidden = true; entrada.setAttribute("aria-expanded", "false"); activo = -1; };
  const marcar = (i) => {
    activo = i;
    [...lista.children].forEach((li, k) => li.setAttribute("aria-selected", String(k === i)));
    if (i >= 0) entrada.setAttribute("aria-activedescendant", lista.children[i].id); else entrada.removeAttribute("aria-activedescendant");
  };
  const ir = (item) => { cerrar(); entrada.value = ""; location.hash = item.hash; entrada.blur(); };
  const pintar = () => {
    items = buscar(entrada.value);
    if (!entrada.value.trim()) return cerrar();
    lista.innerHTML = items.length
      ? items.map((c, i) => `<li role="option" id="res-${i}" data-i="${i}" aria-selected="false"><span>${esc(c.titulo)}<small>${esc(c.sub)}</small></span><b class="num">${esc(c.valor)}</b></li>`).join("")
      : '<li class="sin-resultados" role="presentation">Sin resultados</li>';
    lista.hidden = false; entrada.setAttribute("aria-expanded", "true"); activo = -1;
  };
  entrada.addEventListener("input", pintar);
  entrada.addEventListener("focus", pintar);
  entrada.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" && items.length) { e.preventDefault(); marcar((activo + 1) % items.length); }
    else if (e.key === "ArrowUp" && items.length) { e.preventDefault(); marcar((activo - 1 + items.length) % items.length); }
    else if (e.key === "Enter" && items.length) { e.preventDefault(); ir(items[activo >= 0 ? activo : 0]); }
    else if (e.key === "Escape") { cerrar(); entrada.blur(); }
  });
  lista.addEventListener("mousedown", (e) => { const li = e.target.closest("li[data-i]"); if (li) { e.preventDefault(); ir(items[Number(li.dataset.i)]); } });
  entrada.addEventListener("blur", () => setTimeout(cerrar, 100));
}

// ---------- Piezas de la página ----------
const serieDe = (id) => estado.indice.series.find((s) => s.id === id);

function htmlEncabezado() {
  const tema = document.documentElement.getAttribute("data-theme");
  const n = seriesDemoradas().length;
  const aviso = pipelineAtrasado()
    ? `<a class="aviso-demora" href="#/estado">Datos sin actualizar hace ${Math.floor(horasDesdeGenerado() / 24)} días</a>`
    : n > 0 ? `<a class="aviso-demora" href="#/estado">${n} ${n === 1 ? "serie demorada" : "series demoradas"}</a>` : "";
  return `<header class="contenedor encabezado">
    <a class="marca" href="#/">Monitor Chile<small>La economía chilena en datos</small></a>
    <div class="buscador" role="search">
      <input id="buscar" type="search" placeholder="Buscar: inflación, dólar…  ( / )" autocomplete="off" aria-label="Buscar indicador"
        role="combobox" aria-expanded="false" aria-controls="resultados" aria-autocomplete="list">
      <ul id="resultados" role="listbox" hidden></ul>
    </div>
    <nav class="nav-links" aria-label="Enlaces">
      ${aviso}
      <a class="opcional" href="../">Reporte completo</a>
      <a class="opcional" href="https://datos-economicos-chile.streamlit.app" target="_blank" rel="noopener">Dashboard interactivo ↗</a>
    </nav>
    <button class="boton-icono" id="cambiar-tema" type="button" aria-label="Cambiar entre tema claro y oscuro" title="Cambiar tema">${icono(tema === "dark" ? "sol" : "luna")}</button>
  </header>`;
}

// Cinta de mercado (como la del reporte completo): último dato de las series de mercado con su variación.
function htmlCinta() {
  const items = [["tipo_cambio", "Dólar"], ["ipsa", "IPSA"], ["sp500", "S&P 500"], ["tpm", "TPM"]]
    .map(([id, etq]) => ({ s: serieDe(id), etq })).filter((x) => x.s);
  if (!items.length) return "";
  const una = items.map(({ s, etq }) => {
    const d = s.delta, sube = d !== null && d > 0.005, baja = d !== null && d < -0.005;
    const flecha = sube ? "▲" : baja ? "▼" : "•";
    const variacion = d === null ? "" : fmtDelta(s, d);
    return `<a class="cinta-item" href="#/serie/${esc(s.id)}"><span class="cinta-nombre">${esc(etq)}</span> <b class="num">${fmtValor(s, s.ultimo.valor)}</b>
      <span class="${sube ? "cinta-sube" : baja ? "cinta-baja" : ""} num">${flecha} ${variacion}</span></a>`;
  }).join("");
  return `<div class="cinta" role="region" aria-label="Mercado"><div class="cinta-pista">${una}${una}</div></div>`;
}

function htmlPestanas(activa) {
  const items = [{ id: "", nombre: "Visión general" }, ...todasLasPestanas().map((t) => ({ id: t.id, nombre: t.nombre }))];
  return `<nav class="pestanas" aria-label="Temas y secciones">${items
    .map((t) => `<a class="pestana" href="#/${t.id}" ${t.id === activa ? 'aria-current="page"' : ""}>${esc(t.nombre)}</a>`)
    .join("")}</nav>`;
}

function htmlSelectorVista() {
  return `<div class="vistas" role="group" aria-label="Período que muestran las tarjetas">${VISTAS.map(
    ([id, etq]) => `<button type="button" data-vista="${id}" aria-pressed="${estado.vista === id}">${etq}</button>`
  ).join("")}</div>`;
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
      ? `<div class="dato num">${fmtValor(serie, serie.ultimo.valor)}</div><div class="dato-sub"><a href="#/serie/${esc(serie.id)}">${esc(serie.nombre)}</a> · ${esc(serie.ultimo.etiqueta)}</div>`
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
  const idPrincipal = (tema.vistas && tema.vistas[estado.vista]) || tema.serie;
  const s = serieDe(idPrincipal);
  const filas = tema.secundarias
    .filter((id) => id !== idPrincipal)
    .map((id) => serieDe(id))
    .filter(Boolean)
    .map((x) => {
      const flecha = x.delta === null || Math.abs(x.delta) < 0.05 ? "" : x.delta > 0 ? "▲" : "▼";
      return `<li><a href="#/serie/${esc(x.id)}">${esc(x.nombre)}</a><span class="num">${fmtValor(x, x.ultimo.valor)}<span class="flecha ${claseTono(x.tono)}" aria-label="${x.delta > 0 ? "subió" : "bajó"} respecto al período anterior">${flecha}</span></span></li>`;
    })
    .join("");
  return `<article class="tarjeta">
    <h2 class="tarjeta-titulo">${icono(tema.icono)}<a href="#/${tema.id}">${esc(tema.nombre)}</a></h2>
    <div class="indicador"><a class="enlace-tarjeta" href="#/serie/${esc(s.id)}">${esc(s.nombre)}</a> · ${esc(s.ultimo.etiqueta)}</div>
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
    <div class="indicador"><a class="enlace-tarjeta" href="#/serie/${esc(s.id)}">${esc(s.nombre)}</a> · ${esc(s.ultimo.etiqueta)}</div>
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
    Es información de referencia, no una recomendación de inversión. <a href="#/estado">Estado de los datos</a> · <a href="../">Reporte completo</a> · <a href="https://datos-economicos-chile.streamlit.app" target="_blank" rel="noopener">Dashboard interactivo</a>
  </footer>`;
}

// ---------- Página «Estado de los datos» ----------
function htmlEstado() {
  const temas = Object.fromEntries(todasLasPestanas().map((t) => [t.id, t.nombre]));
  const filas = seriesBase().map((s) => {
    const dias = diasDesde(s.ultimo.fecha);
    return { s, dias, demorada: s.alerta !== false && dias > s.max_dias };
  }).sort((a, b) => Number(b.demorada) - Number(a.demorada) || a.s.tema.localeCompare(b.s.tema));
  const n = filas.filter((f) => f.demorada).length;
  const hora = new Intl.DateTimeFormat("es-CL", { dateStyle: "medium", timeStyle: "short", timeZone: "America/Santiago" }).format(new Date(estado.meta.generado));
  const horas = Math.floor(horasDesdeGenerado());
  return `<div class="migas"><a href="#/">← Monitor</a></div>
    <h1 class="detalle-titulo">Estado de los datos</h1>
    <p class="detalle-def">${n === 0 ? "Todas las series están al día." : `${n} ${n === 1 ? "serie está demorada" : "series están demoradas"}.`}
      Una serie se considera demorada cuando su último dato es más antiguo de lo que corresponde según el calendario de publicación de su fuente.</p>
    <section class="bloque">
      <p class="bloque-nota">Última actualización del sitio: ${esc(hora)} (hace ${horas < 1 ? "menos de una hora" : horas + " h"}).${pipelineAtrasado() ? " <strong>El sitio no se actualiza hace más de 3 días: revisar el workflow en GitHub Actions.</strong>" : ""}</p>
      <div class="tabla-ancha"><table class="tabla-datos izq">
        <caption class="solo-lectores">Antigüedad del último dato de cada serie</caption>
        <thead><tr><th scope="col">Indicador</th><th scope="col">Tema</th><th scope="col">Fuente</th><th scope="col">Último dato</th><th scope="col">Antigüedad</th><th scope="col">Límite esperado</th><th scope="col">Estado</th></tr></thead>
        <tbody>${filas.map(({ s, dias, demorada }) => `<tr>
          <td><a href="#/serie/${esc(s.id)}">${esc(s.nombre)}</a></td><td>${esc(temas[s.tema] || "")}</td><td>${esc(s.fuente)}</td>
          <td>${esc(s.ultimo.etiqueta)}</td><td class="num">${dias} d</td><td class="num">${s.max_dias} d</td>
          <td class="${demorada ? "tono-igual" : "tono-mejor"}"><b>${demorada ? "Demorada" : s.alerta === false ? "Sin seguimiento (fuente discontinua)" : "Al día"}</b></td></tr>`).join("")}</tbody>
      </table></div>
    </section>`;
}

// ---------- Página de detalle de un indicador ----------
const RANGOS = [["1A", 1], ["3A", 3], ["5A", 5], ["Todo", null]];

function recortar(datos, anios) {
  if (!anios) return datos;
  const corte = new Date(datos[datos.length - 1][0] + "T00:00:00Z");
  corte.setUTCFullYear(corte.getUTCFullYear() - anios);
  const iso = corte.toISOString().slice(0, 10);
  return datos.filter((p) => p[0] >= iso);
}

function etiquetaEje(iso, frecuencia) {
  const [a, m, d] = iso.split("-");
  if (frecuencia === "A") return a;
  if (frecuencia === "D") return `${Number(d)} ${MESES[Number(m) - 1]} ${a.slice(2)}`;
  return `${MESES[Number(m) - 1]} ${a.slice(2)}`;
}

function opcionGrande(serie, detalle, anios) {
  const datos = recortar(detalle.datos, anios);
  const valores = datos.map((p) => p[1]);
  const numericos = valores.filter((v) => v !== null);
  const min = Math.min(...numericos), max = Math.max(...numericos);
  const decEje = max - min < 10 ? 1 : 0;
  const acento = css("--accent"), muted = css("--muted");
  const barras = detalle.tipo === "barras";
  const lineasRef = [];
  if (detalle.meta !== null && detalle.meta !== undefined) {
    lineasRef.push({ yAxis: detalle.meta, label: { formatter: `Meta ${numero(detalle.meta, 0)}%`, color: muted, position: "insideEndTop" } });
  }
  if (min < 0 && max > 0) lineasRef.push({ yAxis: 0, label: { show: false } });
  return {
    animation: false,
    grid: { left: 52, right: 22, top: 18, bottom: 30 },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: css("--card-2"), borderColor: css("--border-fuerte"),
      textStyle: { color: css("--text"), fontSize: 13 },
      axisPointer: { type: barras ? "shadow" : "line", lineStyle: { color: muted, type: "dashed" } },
      formatter: (p) => (p[0].value === null || p[0].value === undefined ? "" : `${etiquetaFecha(p[0].axisValue, detalle.frecuencia)}<br><b>${fmtValor(detalle, p[0].value)}</b>`),
    },
    xAxis: {
      type: "category", data: datos.map((p) => p[0]), boundaryGap: barras,
      axisLine: { lineStyle: { color: css("--border-fuerte") } }, axisTick: { show: false },
      axisLabel: { color: muted, hideOverlap: true, formatter: (v) => etiquetaEje(v, detalle.frecuencia) },
    },
    yAxis: {
      type: "value", scale: !barras,
      splitLine: { lineStyle: { color: css("--border") } },
      axisLabel: { color: muted, formatter: (v) => numero(v, decEje) + (detalle.unidad === "%" ? "%" : "") },
    },
    series: [{
      type: barras ? "bar" : "line",
      data: barras
        ? valores.map((v) => ({ value: v, itemStyle: { color: v >= 0 ? acento : css("--igual"), borderRadius: v >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] } }))
        : valores,
      showSymbol: !barras && datos.length <= 60, symbolSize: 6, lineStyle: { width: 2.2, color: acento }, itemStyle: { color: acento },
      areaStyle: barras ? undefined : { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: acento + "40" }, { offset: 1, color: acento + "00" }]) },
      markPoint: barras ? undefined : { silent: true, symbol: "circle", symbolSize: 9, itemStyle: { color: acento }, label: { show: false }, data: [{ coord: [datos.length - 1, valores[valores.length - 1]] }] },
      markLine: lineasRef.length ? { silent: true, symbol: "none", lineStyle: { color: muted, type: "dashed", opacity: 0.6 }, data: lineasRef } : undefined,
    }],
  };
}

function dibujarGrande(contenedor, serie, detalle, anios) {
  const grafico = echarts.init(contenedor, null, { renderer: "canvas" });
  grafico.setOption(opcionGrande(serie, detalle, anios));
  const observador = new ResizeObserver(() => grafico.resize());
  observador.observe(contenedor);
  estado.graficos.push({ grafico, observador });
  return grafico;
}

function descargarCSV(detalle) {
  const filas = ["fecha,valor", ...detalle.datos.map((p) => `${p[0]},${p[1]}`)];
  const url = URL.createObjectURL(new Blob([filas.join("\n") + "\n"], { type: "text/csv;charset=utf-8" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: `${detalle.id}.csv` });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function htmlTabla(serie, detalle) {
  const ultimos = detalle.datos.slice(-13);
  const filas = [];
  for (let i = ultimos.length - 1; i >= 1; i--) {
    const delta = serie.delta_tipo === "pp" ? ultimos[i][1] - ultimos[i - 1][1]
      : ultimos[i - 1][1] ? (ultimos[i][1] / ultimos[i - 1][1] - 1) * 100 : null;
    filas.push(`<tr><td>${etiquetaFecha(ultimos[i][0], serie.frecuencia)}</td><td class="num">${fmtValor(serie, ultimos[i][1])}</td><td class="num">${fmtDelta(serie, delta)}</td></tr>`);
  }
  return `<table class="tabla-datos"><caption class="solo-lectores">Últimos datos de ${esc(serie.nombre)}</caption>
    <thead><tr><th scope="col">Período</th><th scope="col">Valor</th><th scope="col">Cambio vs. anterior</th></tr></thead><tbody>${filas.join("")}</tbody></table>`;
}

function htmlRevisiones(detalle) {
  const rev = detalle.revisiones || [];
  if (!rev.length) return "";
  const fmt = (r, v) => numero(v, 2) + (r.unidad === "%" ? "%" : "");
  const fuentes = [...new Set(rev.map((r) => r.serie))].join(", ");
  return `<section class="bloque" aria-labelledby="t-rev"><h2 id="t-rev">Revisiones de datos</h2>
    <p class="bloque-nota">Las fuentes oficiales revisan cifras de períodos anteriores. El gráfico usa siempre el valor vigente; acá queda el valor
      anterior de cada revisión detectada. Valores de «${esc(fuentes)}», la serie original de la que sale este indicador.</p>
    <div class="tabla-ancha"><table class="tabla-datos izq"><caption class="solo-lectores">Revisiones detectadas</caption>
      <thead><tr><th scope="col">Serie</th><th scope="col">Período</th><th scope="col">Valor anterior</th><th scope="col">Valor nuevo</th><th scope="col">Detectado</th></tr></thead>
      <tbody>${rev.map((r) => `<tr><td>${esc(r.serie)}</td><td>${etiquetaFecha(r.fecha, detalle.frecuencia)}</td><td class="num">${fmt(r, r.anterior)}</td><td class="num">${fmt(r, r.nuevo)}</td><td class="num">${r.detectado.split("-").reverse().join("-")}</td></tr>`).join("")}</tbody>
    </table></div></section>`;
}

function htmlDetalle(serie, detalle) {
  const tema = todasLasPestanas().find((t) => t.id === serie.tema);
  const url = location.href.split("#")[0] + "#/serie/" + serie.id;
  const texto = `${serie.nombre}: ${fmtValor(serie, serie.ultimo.valor)} (${serie.ultimo.etiqueta})`;
  const enc = encodeURIComponent;
  const relacionados = estado.indice.series.filter((x) => x.tema === serie.tema && x.id !== serie.id);
  const porDefecto = serie.frecuencia === "D" ? 1 : 5;
  return `<div class="migas"><a href="#/${esc(serie.tema)}">← Monitor · ${esc(tema ? tema.nombre : "")}</a></div>
    <h1 class="detalle-titulo">${esc(serie.nombre)}</h1>
    <p class="detalle-def">${esc(detalle.definicion)}</p>
    <div class="detalle-grid">
      <aside>
        <div class="tarjeta">
          <div class="indicador">${esc(serie.nombre)}</div>
          <div class="valor num">${fmtValor(serie, serie.ultimo.valor)}</div>
          <div class="indicador">${esc(serie.ultimo.etiqueta)}</div>
          ${htmlTono(serie)}
          <div class="mini" data-serie="${esc(serie.id)}" role="img" aria-label="Evolución reciente"></div>
          <div class="fuente">Fuente: ${esc(serie.fuente)}</div>
        </div>
        <div class="compartir" role="group" aria-label="Compartir">
          <a class="boton-chico" target="_blank" rel="noopener" href="https://wa.me/?text=${enc(texto + " " + url)}">WhatsApp</a>
          <a class="boton-chico" target="_blank" rel="noopener" href="https://twitter.com/intent/tweet?text=${enc(texto)}&url=${enc(url)}">X</a>
          <a class="boton-chico" target="_blank" rel="noopener" href="https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}">LinkedIn</a>
          <a class="boton-chico" target="_blank" rel="noopener" href="https://t.me/share/url?url=${enc(url)}&text=${enc(texto)}">Telegram</a>
          <button class="boton-chico" type="button" id="copiar-enlace">Copiar enlace</button>
        </div>
      </aside>
      <section class="bloque grande" aria-label="Gráfico">
        <div class="bloque-cabecera">
          <h2>${esc(serie.nombre)}</h2>
          <div class="rangos" role="group" aria-label="Rango de tiempo">${RANGOS.map(([etq, a]) => `<button type="button" data-anios="${a ?? ""}" aria-pressed="${a === porDefecto}">${etq}</button>`).join("")}</div>
        </div>
        <div class="grande-grafico" id="grafico-grande" role="img" aria-label="Gráfico de ${esc(serie.nombre)}"></div>
      </section>
    </div>
    <section class="bloque" aria-labelledby="t-tabla">
      <div class="bloque-cabecera"><h2 id="t-tabla">Últimos datos</h2><button class="boton-chico" type="button" id="bajar-csv">Descargar serie completa (CSV)</button></div>
      ${htmlTabla(serie, detalle)}
    </section>
    ${htmlRevisiones(detalle)}
    ${relacionados.length ? `<section class="bloque" aria-labelledby="t-rel"><h2 id="t-rel">Otros indicadores de ${esc(tema ? tema.nombre : "")}</h2>
      <ul class="relacionados">${relacionados.map((x) => `<li><a href="#/serie/${esc(x.id)}"><span>${esc(x.nombre)}</span><span class="num">${fmtValor(x, x.ultimo.valor)}</span></a></li>`).join("")}</ul></section>` : ""}`;
}

function activarDetalle(serie, detalle) {
  const contenedor = document.getElementById("grafico-grande");
  let anios = serie.frecuencia === "D" ? 1 : 5;
  const grafico = dibujarGrande(contenedor, serie, detalle, anios);
  document.querySelectorAll(".rangos button").forEach((b) =>
    b.addEventListener("click", () => {
      anios = b.dataset.anios ? Number(b.dataset.anios) : null;
      document.querySelectorAll(".rangos button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      grafico.setOption(opcionGrande(serie, detalle, anios), true);
    })
  );
  document.getElementById("bajar-csv").addEventListener("click", () => descargarCSV(detalle));
  const copiar = document.getElementById("copiar-enlace");
  copiar.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(location.href);
      copiar.textContent = "¡Copiado!";
    } catch (e) {
      copiar.textContent = "Copia la URL de la barra";
    }
    setTimeout(() => (copiar.textContent = "Copiar enlace"), 2000);
  });
}

// ---------- Gráficos compuestos y secciones ----------
const PALETA = () => [css("--accent"), "#e8c15a", "#5fd38d", "#f08a7a", "#c792ea", "#5ec4c4"];
const CONFIGURABLE_EN_TIEMPO = (g) => ["lineas", "barras_apiladas", "proyeccion"].includes(g.tipo) && g.frecuencia !== "A";

function unirFechas(listas) {
  return [...new Set(listas.flat().map((p) => p[0]))].sort();
}
function alinear(datos, fechas) {
  const m = new Map(datos.map((p) => [p[0], p[1]]));
  return fechas.map((f) => (m.has(f) ? m.get(f) : null));
}
function corteIso(g, anios) {
  if (!anios) return "0000-00-00";
  const ultimas = g.series.map((s) => s.datos[s.datos.length - 1][0]).sort();
  const c = new Date(ultimas[ultimas.length - 1] + "T00:00:00Z");
  c.setUTCFullYear(c.getUTCFullYear() - anios);
  return c.toISOString().slice(0, 10);
}

function tooltipCompuesto(g, extra) {
  return {
    trigger: "axis", confine: true, backgroundColor: css("--card-2"), borderColor: css("--border-fuerte"),
    textStyle: { color: css("--text"), fontSize: 13 },
    axisPointer: { type: g.tipo === "barras_apiladas" ? "shadow" : "line", lineStyle: { color: css("--muted"), type: "dashed" } },
    formatter: (ps) => {
      const filas = ps.filter((p) => p.value !== null && p.value !== undefined && !String(p.seriesName).startsWith("__"));
      if (!filas.length) return "";
      const cuerpo = filas.map((p) => `${p.marker} ${esc(p.seriesName)}: <b>${fmtGen(g, p.value)}</b>`).join("<br>");
      return `${etiquetaFecha(ps[0].axisValue, g.frecuencia)}<br>${cuerpo}${extra ? extra(ps[0].axisValue) : ""}`;
    },
  };
}

function ejesTiempo(g, fechas, barras) {
  const muted = css("--muted");
  let min = Infinity, max = -Infinity;
  return {
    xAxis: {
      type: "category", data: fechas, boundaryGap: barras,
      axisLine: { lineStyle: { color: css("--border-fuerte") } }, axisTick: { show: false },
      axisLabel: { color: muted, hideOverlap: true, formatter: (v) => etiquetaEje(v, g.frecuencia) },
    },
    yAxis: {
      type: "value", scale: !barras, splitLine: { lineStyle: { color: css("--border") } },
      axisLabel: { color: muted, formatter: (v) => fmtGen({ ...g, decimales: Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0 }, v) },
    },
  };
}

function referencias(g, valores) {
  const muted = css("--muted"), refs = [];
  if (g.meta !== null && g.meta !== undefined) refs.push({ yAxis: g.meta, label: { formatter: `Meta ${numero(g.meta, 0)}%`, color: muted, position: "insideEndTop" } });
  const nums = valores.filter((v) => v !== null && v !== undefined);
  if (nums.length && Math.min(...nums) < 0 && Math.max(...nums) > 0) refs.push({ yAxis: 0, label: { show: false } });
  return refs.length ? { silent: true, symbol: "none", lineStyle: { color: muted, type: "dashed", opacity: 0.6 }, data: refs } : undefined;
}

function opcionRanking(g) {
  const filas = [...g.filas].sort((a, b) => a.valor - b.valor), acento = css("--accent");
  return {
    animation: false,
    grid: { left: 8, right: 64, top: 8, bottom: 8, containLabel: true },
    tooltip: {
      trigger: "item", confine: true, backgroundColor: css("--card-2"), borderColor: css("--border-fuerte"), textStyle: { color: css("--text"), fontSize: 13 },
      formatter: (p) => `${esc(p.name)}: <b>${fmtGen(g, p.value)}</b><br>Año: ${esc(filas[p.dataIndex].anio)}`,
    },
    xAxis: { type: "value", splitLine: { lineStyle: { color: css("--border") } }, axisLabel: { color: css("--muted"), formatter: (v) => fmtGen({ ...g, decimales: 0 }, v) } },
    yAxis: {
      type: "category", data: filas.map((f) => f.nombre), axisTick: { show: false }, axisLine: { show: false },
      axisLabel: { fontSize: 11, interval: 0, color: (_v, i) => (filas[i] && filas[i].destacado ? acento : css("--muted")), fontWeight: "normal" },
    },
    series: [{
      type: "bar", barMaxWidth: 16,
      data: filas.map((f) => ({ value: f.valor, itemStyle: { color: f.destacado ? acento : css("--border-fuerte"), borderRadius: [0, 3, 3, 0] } })),
      label: { show: true, position: "right", color: css("--muted"), fontSize: 11, formatter: (p) => fmtGen(g, p.value) },
    }],
  };
}

function opcionCompuesta(g, anios) {
  if (g.tipo === "ranking") return opcionRanking(g);
  const cols = PALETA(), corte = corteIso(g, anios);
  const cortar = (datos) => datos.filter((p) => p[0] >= corte);
  const leyenda = (data) => ({ top: 0, left: 0, textStyle: { color: css("--muted") }, data, icon: "roundRect", itemWidth: 12, itemHeight: 6 });
  const grid = { left: 56, right: 22, top: 40, bottom: 30 };

  if (g.tipo === "proyeccion") {
    const hist = cortar(g.series[0].datos), proy = g.proyeccion.datos;
    const fechas = unirFechas([hist, proy]);
    const ultimoHist = hist[hist.length - 1];
    const dProy = alinear(proy.map((p) => [p[0], p[1]]), fechas);
    dProy[fechas.indexOf(ultimoHist[0])] = ultimoHist[1]; // la proyección arranca pegada al histórico
    const lo = alinear(proy.map((p) => [p[0], p[2]]), fechas), hi = alinear(proy.map((p) => [p[0], p[3]]), fechas);
    const banda = fechas.map((_, i) => (lo[i] === null ? null : hi[i] - lo[i]));
    const base = fechas.map((_, i) => lo[i]);
    const rango = new Map(proy.map((p) => [p[0], [p[2], p[3]]]));
    const naranja = "#f0a97c";
    return {
      animation: false, grid, legend: leyenda([g.series[0].nombre, g.proyeccion.nombre, g.proyeccion.banda]),
      tooltip: tooltipCompuesto(g, (f) => (rango.has(f) ? `<br>${g.proyeccion.banda}: ${fmtGen(g, rango.get(f)[0])} a ${fmtGen(g, rango.get(f)[1])}` : "")),
      ...ejesTiempo(g, fechas, false),
      series: [
        { name: "__base", type: "line", data: base, stack: "banda", symbol: "none", lineStyle: { opacity: 0 }, silent: true, connectNulls: true },
        { name: g.proyeccion.banda, type: "line", data: banda, stack: "banda", symbol: "none", lineStyle: { opacity: 0 }, itemStyle: { color: naranja }, areaStyle: { color: naranja + "33" }, silent: true, connectNulls: true },
        { name: g.series[0].nombre, type: "line", data: alinear(hist, fechas), showSymbol: false, lineStyle: { width: 2.2, color: cols[0] }, itemStyle: { color: cols[0] }, markLine: referencias(g, hist.map((p) => p[1])) },
        { name: g.proyeccion.nombre, type: "line", data: dProy, showSymbol: false, lineStyle: { width: 2.2, color: naranja, type: "dashed" }, itemStyle: { color: naranja } },
      ],
    };
  }

  const ss = g.series.map((s) => ({ ...s, datos: cortar(s.datos) }));
  const fechas = unirFechas(ss.map((s) => s.datos));
  if (g.tipo === "barras_apiladas") {
    const total = cortar(g.total.datos);
    return {
      animation: false, grid, legend: leyenda([...ss.map((s) => s.nombre), g.total.nombre]),
      tooltip: tooltipCompuesto(g), ...ejesTiempo(g, fechas, true),
      series: [
        ...ss.map((s, i) => ({ name: s.nombre, type: "bar", stack: "aportes", data: alinear(s.datos, fechas), itemStyle: { color: s.color || cols[i % cols.length] } })),
        { name: g.total.nombre, type: "line", data: alinear(total, fechas), showSymbol: false, lineStyle: { width: 2, color: css("--text") }, itemStyle: { color: css("--text") }, z: 5, markLine: referencias(g, [-1, 1]) },
      ],
    };
  }
  const todos = ss.flatMap((s) => s.datos.map((p) => p[1]));
  return {
    animation: false, grid, legend: ss.length > 1 ? leyenda(ss.map((s) => s.nombre)) : undefined,
    tooltip: tooltipCompuesto(g), ...ejesTiempo(g, fechas, false),
    series: ss.map((s, i) => ({
      name: s.nombre, type: "line", data: alinear(s.datos, fechas), connectNulls: true, showSymbol: fechas.length <= 40, symbolSize: 5,
      lineStyle: { width: 2.2, color: s.color || cols[i % cols.length] }, itemStyle: { color: s.color || cols[i % cols.length] },
      markLine: i === 0 ? referencias(g, todos) : undefined,
    })),
  };
}

function htmlBloquesGraficos(ids) {
  return (ids || []).map((id) => {
    const g = (estado.indice.graficos || []).find((x) => x.id === id);
    if (!g) return "";
    const rangos = CONFIGURABLE_EN_TIEMPO(g)
      ? `<div class="rangos" role="group" aria-label="Rango de tiempo">${RANGOS.map(([etq, a]) => `<button type="button" data-anios="${a ?? ""}" aria-pressed="${a === 5}">${etq}</button>`).join("")}</div>`
      : "";
    return `<section class="bloque" id="g-${esc(g.id)}" aria-labelledby="h-${esc(g.id)}">
      <div class="bloque-cabecera"><h2 id="h-${esc(g.id)}">${esc(g.nombre)}</h2>${rangos}</div>
      <p class="bloque-nota">${esc(g.definicion)}${g.enlace ? ` <a class="enlace-bloque" href="${esc(g.enlace.hash)}">${esc(g.enlace.texto)}</a>` : ""}</p>
      <p class="callout" hidden></p>
      <div class="grafico-compuesto" data-g="${esc(g.id)}" role="img" aria-label="${esc(g.nombre)}"></div>
    </section>`;
  }).join("");
}

async function activarCompuestos(idRender) {
  const contenedores = [...document.querySelectorAll(".grafico-compuesto")];
  await Promise.all(contenedores.map(async (el) => {
    let g;
    try { g = await cargarCompuesto(el.dataset.g); } catch (e) { el.textContent = "No se pudo cargar este gráfico."; return; }
    if (idRender !== estado.renderId || !el.isConnected) return;
    const seccion = el.closest("section");
    let anios = g.frecuencia === "A" ? null : 5;
    el.style.height = g.tipo === "ranking" ? `${g.filas.length * 22 + 30}px` : "380px";
    if (g.callout) { const c = seccion.querySelector(".callout"); c.textContent = g.callout; c.hidden = false; }
    const grafico = echarts.init(el, null, { renderer: "canvas" });
    grafico.setOption(opcionCompuesta(g, anios));
    const observador = new ResizeObserver(() => grafico.resize());
    observador.observe(el);
    estado.graficos.push({ grafico, observador });
    seccion.querySelectorAll(".rangos button").forEach((b) =>
      b.addEventListener("click", () => {
        anios = b.dataset.anios ? Number(b.dataset.anios) : null;
        seccion.querySelectorAll(".rangos button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        grafico.setOption(opcionCompuesta(g, anios), true);
      })
    );
  }));
}

function htmlTablaRevisiones(filas, columnas) {
  if (!filas.length) return '<p class="bloque-nota">Sin revisiones registradas todavía.</p>';
  return `<div class="tabla-ancha"><table class="tabla-datos izq"><thead><tr>${columnas.map((c) => `<th scope="col">${esc(c)}</th>`).join("")}</tr></thead>
    <tbody>${filas.map((f) => `<tr>${columnas.map((c) => `<td>${esc(f[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function activarRevisiones(idRender) {
  const cont = document.getElementById("revisiones-contenido");
  if (!cont) return;
  let r;
  try { r = await cargarRevisiones(); } catch (e) { cont.textContent = "No se pudieron cargar las revisiones."; return; }
  if (idRender !== estado.renderId) return;
  cont.innerHTML = `<h2>Resumen (últimos 90 días)</h2>${htmlTablaRevisiones(r.resumen, ["Detectado", "Serie", "Períodos revisados", "Desde", "Hasta", "Mayor cambio (%)"])}
    <h2>Los 15 cambios individuales más grandes</h2>${htmlTablaRevisiones(r.mayores, ["Serie", "Período", "Valor anterior", "Valor nuevo", "Cambio (%)", "Detectado"])}`;
}

function htmlPestana(id) {
  const tema = estado.indice.temas.find((t) => t.id === id), seccion = (estado.indice.secciones || []).find((t) => t.id === id);
  const entrada = tema || seccion;
  const series = tema ? estado.indice.series.filter((s) => s.tema === id) : (seccion.series || []).map(serieDe).filter(Boolean);
  const cabecera = seccion ? `<h1 class="detalle-titulo">${esc(seccion.nombre)}</h1><p class="detalle-def">${esc(seccion.intro || "")}</p>` : "";
  // En un tema con muchos indicadores: primero los principales, luego los gráficos de análisis y al final el resto.
  const principalesIds = tema ? [...new Set([tema.serie, ...Object.values(tema.vistas || {}), ...tema.secundarias])] : series.map((s) => s.id);
  const principales = principalesIds.map(serieDe).filter(Boolean);
  const otros = series.filter((s) => !principalesIds.includes(s.id));
  const tarjetas = principales.length ? `<div class="rejilla">${principales.map(htmlTarjetaSerie).join("")}</div>` : "";
  const masIndicadores = otros.length ? `<h2 class="subtitulo">Más indicadores</h2><div class="rejilla">${otros.map(htmlTarjetaSerie).join("")}</div>` : "";
  const extra = seccion && seccion.tipo === "revisiones" ? '<section class="bloque" id="revisiones-contenido" aria-live="polite">Cargando…</section>'
    : seccion && seccion.tipo === "comparador" ? htmlComparador() : "";
  return `${cabecera}${tarjetas}${htmlBloquesGraficos(entrada.graficos)}${masIndicadores}${extra}`;
}

// ---------- Comparador de países ----------
const COMP_MAX = 8;
const COMP_DEFECTO = ["CHL", "OED", "WLD"];
const COMP_INDICADORES = [["crecimiento_pib", "Crecimiento del PIB"], ["crecimiento_pib_pc", "PIB per cápita"], ["inflacion", "Inflación"], ["desempleo", "Desempleo"]];
const COMP_RANGOS = [["10 años", 10], ["20 años", 20], ["Desde 1990", null]];
const COMP_RAPIDOS = ["ARG", "BRA", "PER", "MEX", "COL", "USA", "CHN", "LCN", "EUU", "DEU"];
const COMP_COLORES = ["#e8c15a", "#5fd38d", "#f08a7a", "#c792ea", "#5ec4c4", "#f0a97c", "#9aa5b8"];
const comp = { ind: "crecimiento_pib", sel: [...COMP_DEFECTO], anios: 20, entidades: null, datos: {}, grafico: null };

const compColor = (codigo) => (codigo === "CHL" ? css("--accent") : COMP_COLORES[(comp.sel.filter((c) => c !== "CHL").indexOf(codigo)) % COMP_COLORES.length]);
const compNombre = (codigo) => (comp.entidades.find((e) => e.id === codigo) || { nombre: codigo }).nombre;

function compDesdeQuery(query) {
  if (!query) return;
  const p = new URLSearchParams(query);
  if (COMP_INDICADORES.some(([id]) => id === p.get("i"))) comp.ind = p.get("i");
  if (p.get("p")) comp.sel = ["CHL", ...p.get("p").split(",").filter((c) => c && c !== "CHL")].slice(0, COMP_MAX);
  if (p.get("a")) comp.anios = p.get("a") === "todo" ? null : Number(p.get("a")) || 20;
}
const compHash = () => `#/comparador?i=${comp.ind}&p=${comp.sel.filter((c) => c !== "CHL").join(",")}&a=${comp.anios ?? "todo"}`;

function htmlComparador() {
  return `<section class="bloque" id="comparador-bloque" aria-label="Comparador">
    <div class="comp-controles">
      <div class="rangos" id="comp-indicador" role="group" aria-label="Indicador">${COMP_INDICADORES.map(([id, etq]) => `<button type="button" data-ind="${id}">${etq}</button>`).join("")}</div>
      <div class="rangos" id="comp-rango" role="group" aria-label="Período">${COMP_RANGOS.map(([etq, a]) => `<button type="button" data-anios="${a ?? "todo"}">${etq}</button>`).join("")}</div>
    </div>
    <ul class="chips" id="comp-chips" aria-label="Países y regiones seleccionados"></ul>
    <div class="comp-agregar">
      <input id="comp-buscar" list="comp-lista" type="text" placeholder="Agregar país o región (ej. Argentina, Zona del Euro)…" autocomplete="off" aria-label="Agregar país o región">
      <datalist id="comp-lista"></datalist>
      <button class="boton-chico" type="button" id="comp-reset">Chile vs. OCDE y mundo</button>
    </div>
    <div class="comp-rapidos" id="comp-rapidos" aria-label="Agregar rápido"></div>
    <p class="callout" id="comp-resumen" hidden></p>
    <div class="grafico-compuesto" id="comp-grafico" style="height:420px" role="img" aria-label="Comparación entre países"></div>
    <div class="bloque-cabecera" style="margin-top:18px"><h2>Promedios</h2><button class="boton-chico" type="button" id="comp-csv">Descargar CSV</button></div>
    <div class="tabla-ancha" id="comp-tabla"></div>
    <p class="bloque-nota" id="comp-nota"></p>
  </section>`;
}

async function cargarComparador(ind) {
  const v = estado.meta.generado;
  if (!comp.entidades) comp.entidades = await pedirJSON("comparador/entidades.json", v);
  if (!comp.datos[ind]) comp.datos[ind] = await pedirJSON(`comparador/${ind}.json`, v);
  return comp.datos[ind];
}

const compSerie = (d, codigo) => d.datos[codigo] || null;
const compFmt = (d, v) => (v === null || v === undefined ? "—" : fmtGen({ unidad: d.unidad, decimales: d.decimales }, v));

function compPromedio(d, codigo, n) {
  const serie = compSerie(d, codigo);
  if (!serie) return null;
  const ultimo = d.anios.length - 1;
  const desde = n === null ? 0 : Math.max(0, ultimo - n + 1);
  const vals = serie.slice(desde).filter((v) => v !== null);
  return vals.length >= (n === null ? 3 : Math.ceil(n / 2)) ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
}

function compResumen(d) {
  const ultimo = d.anios.length - 1, anio = d.anios[ultimo];
  const chile = compSerie(d, "CHL");
  if (!chile || chile[ultimo] === null) return "";
  const v = chile[ultimo];
  const paises = comp.entidades.filter((e) => e.tipo === "pais" && d.datos[e.id] && d.datos[e.id][ultimo] !== null);
  const puesto = paises.filter((e) => d.datos[e.id][ultimo] > v).length + 1;
  const ref = (cod, nombre) => (compSerie(d, cod) && compSerie(d, cod)[ultimo] !== null ? { nombre, v: compSerie(d, cod)[ultimo] } : null);
  const refs = [ref("OED", "la OCDE"), ref("WLD", "el mundo")].filter(Boolean);
  const verbo = d.id.startsWith("crecimiento") ? "creció" : d.id === "inflacion" ? "tuvo una inflación de" : "tuvo un desempleo de";
  const comparaciones = refs.map((r) => {
    const mas = d.id.startsWith("crecimiento") ? "más que" : "más que";
    return `${v > r.v ? mas : v < r.v ? "menos que" : "igual que"} ${r.nombre} (${compFmt(d, r.v)})`;
  });
  const frase = `En ${anio} Chile ${verbo} ${compFmt(d, v)}${comparaciones.length ? ": " + comparaciones.join(" y ") : ""}.`;
  return `${frase} Entre ${paises.length} países con dato ocupa el lugar ${puesto} (ordenados de mayor a menor).`;
}

function compPintar() {
  const d = comp.datos[comp.ind];
  if (!d) return;
  const cont = document.getElementById("comp-grafico");
  if (!cont) return;
  // controles
  document.querySelectorAll("#comp-indicador button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.ind === comp.ind)));
  document.querySelectorAll("#comp-rango button").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.anios === "todo" ? null : Number(b.dataset.anios)) === comp.anios)));
  // chips
  document.getElementById("comp-chips").innerHTML = comp.sel.map((c) => `<li class="chip" style="--color:${compColor(c)}"><span class="punto-color"></span>${esc(compNombre(c))}${c === "CHL" ? "" : `<button type="button" data-quitar="${esc(c)}" aria-label="Quitar ${esc(compNombre(c))}">×</button>`}</li>`).join("");
  // atajos
  const rapidos = COMP_RAPIDOS.filter((c) => !comp.sel.includes(c) && comp.entidades.some((e) => e.id === c));
  document.getElementById("comp-rapidos").innerHTML = rapidos.length ? `<span>Agregar:</span> ${rapidos.map((c) => `<button type="button" class="boton-chico" data-agregar="${esc(c)}">+ ${esc(compNombre(c))}</button>`).join("")}` : "";
  // resumen
  const resumen = document.getElementById("comp-resumen");
  resumen.textContent = compResumen(d); resumen.hidden = !resumen.textContent;
  // gráfico
  const n = comp.anios;
  const desde = n === null ? 0 : Math.max(0, d.anios.length - n);
  const anios = d.anios.slice(desde);
  const series = comp.sel.map((c) => ({ c, datos: (compSerie(d, c) || []).slice(desde) })).filter((s) => s.datos.length);
  const todos = series.flatMap((s) => s.datos).filter((v) => v !== null);
  const cruza = todos.length && Math.min(...todos) < 0 && Math.max(...todos) > 0;
  if (!comp.grafico) {
    comp.grafico = echarts.init(cont, null, { renderer: "canvas" });
    const obs = new ResizeObserver(() => comp.grafico.resize());
    obs.observe(cont);
    estado.graficos.push({ grafico: comp.grafico, observador: obs });
  }
  const g = { unidad: d.unidad, decimales: d.decimales, frecuencia: "A" };
  comp.grafico.setOption({
    animation: false, grid: { left: 52, right: 22, top: 40, bottom: 30 },
    legend: { top: 0, left: 0, textStyle: { color: css("--muted") }, icon: "roundRect", itemWidth: 12, itemHeight: 6 },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: css("--card-2"), borderColor: css("--border-fuerte"), textStyle: { color: css("--text"), fontSize: 13 },
      axisPointer: { type: "line", lineStyle: { color: css("--muted"), type: "dashed" } },
      formatter: (ps) => `${ps[0].axisValue}<br>${[...ps].filter((p) => p.value !== null && p.value !== undefined).sort((a, b) => b.value - a.value)
        .map((p) => `${p.marker} ${esc(p.seriesName)}: <b>${fmtGen(g, p.value)}</b>`).join("<br>")}`,
    },
    xAxis: { type: "category", data: anios.map(String), boundaryGap: false, axisLine: { lineStyle: { color: css("--border-fuerte") } }, axisTick: { show: false }, axisLabel: { color: css("--muted"), hideOverlap: true } },
    yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: css("--border") } }, axisLabel: { color: css("--muted"), formatter: (v) => fmtGen({ unidad: d.unidad, decimales: Math.abs(v) < 10 && !Number.isInteger(v) ? 1 : 0 }, v) } },
    series: series.map((s, i) => ({
      name: compNombre(s.c), type: "line", data: s.datos, connectNulls: false, showSymbol: anios.length <= 25, symbolSize: s.c === "CHL" ? 7 : 5,
      lineStyle: { width: s.c === "CHL" ? 3.6 : 2, color: compColor(s.c) }, itemStyle: { color: compColor(s.c) }, z: s.c === "CHL" ? 5 : 2,
      markLine: i === 0 && cruza ? { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: css("--muted"), type: "dashed", opacity: 0.6 }, data: [{ yAxis: 0 }] } : undefined,
    })),
  }, true);
  // tabla de promedios
  const ultimoAnio = d.anios[d.anios.length - 1];
  const cols = [[5, `5 años (${ultimoAnio - 4}-${ultimoAnio})`], [10, `10 años (${ultimoAnio - 9}-${ultimoAnio})`], [20, `20 años (${ultimoAnio - 19}-${ultimoAnio})`], [null, `Desde ${d.anios[0]}`]];
  document.getElementById("comp-tabla").innerHTML = `<table class="tabla-datos izq"><caption class="solo-lectores">Promedios de ${esc(d.nombre)}</caption>
    <thead><tr><th scope="col">País o región</th><th scope="col">${ultimoAnio}</th>${cols.map(([, etq]) => `<th scope="col">Promedio ${esc(etq)}</th>`).join("")}</tr></thead>
    <tbody>${comp.sel.map((c) => { const ser = compSerie(d, c); return `<tr class="${c === "CHL" ? "fila-chile" : ""}"><td><span class="punto-color" style="--color:${compColor(c)}"></span> ${esc(compNombre(c))}</td>
      <td class="num">${compFmt(d, ser ? ser[ser.length - 1] : null)}</td>${cols.map(([n2]) => `<td class="num">${compFmt(d, compPromedio(d, c, n2))}</td>`).join("")}</tr>`; }).join("")}</tbody></table>`;
  document.getElementById("comp-nota").textContent = `${d.descripcion} Fuente: ${d.fuente}. Los promedios son el promedio simple de las tasas anuales de cada período (no la tasa compuesta). `
    + "Las cifras pueden diferir un poco de las oficiales de cada país porque el Banco Mundial las armoniza para que sean comparables. Un guion (—) significa que no hay dato.";
  history.replaceState(null, "", compHash());
}

function compAgregar(codigo) {
  if (comp.sel.includes(codigo)) return;
  const nota = document.getElementById("comp-nota");
  if (comp.sel.length >= COMP_MAX) { nota.textContent = `Máximo ${COMP_MAX} a la vez: quita alguno para agregar otro.`; return; }
  comp.sel.push(codigo);
  compPintar();
}

async function activarComparador(idRender, query) {
  compDesdeQuery(query);
  let d;
  try { d = await cargarComparador(comp.ind); } catch (e) { const c = document.getElementById("comparador-bloque"); if (c) c.textContent = "No se pudieron cargar los datos del comparador."; return; }
  if (idRender !== estado.renderId || !document.getElementById("comp-grafico")) return;
  comp.grafico = null;
  document.getElementById("comp-lista").innerHTML = [...comp.entidades].sort((a, b) => a.nombre.localeCompare(b.nombre, "es"))
    .map((e) => `<option value="${esc(e.nombre)}">${e.tipo === "agregado" ? "Región o grupo" : esc(e.region)}</option>`).join("");
  const buscarEntidad = (texto) => {
    const t = norm(texto).trim();
    if (!t) return null;
    return comp.entidades.find((e) => norm(e.nombre) === t) || (comp.entidades.filter((e) => norm(e.nombre).startsWith(t)).length === 1 ? comp.entidades.find((e) => norm(e.nombre).startsWith(t)) : null);
  };
  const entrada = document.getElementById("comp-buscar");
  const intentar = () => { const e = buscarEntidad(entrada.value); if (e) { entrada.value = ""; compAgregar(e.id); } };
  entrada.addEventListener("change", intentar);
  entrada.addEventListener("keydown", (ev) => { if (ev.key === "Enter") { ev.preventDefault(); intentar(); } });
  document.getElementById("comp-chips").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-quitar]");
    if (b) { comp.sel = comp.sel.filter((c) => c !== b.dataset.quitar); compPintar(); }
  });
  document.getElementById("comp-rapidos").addEventListener("click", (ev) => { const b = ev.target.closest("[data-agregar]"); if (b) compAgregar(b.dataset.agregar); });
  document.getElementById("comp-reset").addEventListener("click", () => { comp.sel = [...COMP_DEFECTO]; compPintar(); });
  document.getElementById("comp-rango").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-anios]");
    if (b) { comp.anios = b.dataset.anios === "todo" ? null : Number(b.dataset.anios); compPintar(); }
  });
  document.getElementById("comp-indicador").addEventListener("click", async (ev) => {
    const b = ev.target.closest("[data-ind]");
    if (!b || b.dataset.ind === comp.ind) return;
    try { await cargarComparador(b.dataset.ind); } catch (e) { return; }
    comp.ind = b.dataset.ind; compPintar();
  });
  document.getElementById("comp-csv").addEventListener("click", () => {
    const dd = comp.datos[comp.ind];
    const filas = [["año", ...comp.sel.map(compNombre)].join(","), ...dd.anios.map((a, i) => [a, ...comp.sel.map((c) => { const s = compSerie(dd, c); return s && s[i] !== null ? s[i] : ""; })].join(","))];
    const url = URL.createObjectURL(new Blob([filas.join("\n") + "\n"], { type: "text/csv;charset=utf-8" }));
    const a = Object.assign(document.createElement("a"), { href: url, download: `comparador_${comp.ind}.csv` });
    document.body.appendChild(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  compPintar();
}

// ---------- Render ----------
function rutaActual() {
  const [camino, query] = location.hash.replace(/^#\/?/, "").split("?");
  const partes = camino.split("/").map(decodeURIComponent);
  if (partes[0] === "serie") {
    const serie = serieDe(partes[1]);
    if (serie) return { tipo: "serie", serie, tema: serie.tema };
  }
  if (partes[0] === "estado") return { tipo: "estado", tema: null };
  if (todasLasPestanas().some((t) => t.id === partes[0])) return { tipo: "tab", tema: partes[0], grafico: partes[1] || null, query: query || "" };
  return { tipo: "home", tema: "" };
}

async function render() {
  const id = ++estado.renderId;
  const ruta = rutaActual();
  let cuerpo, detalle = null;
  if (ruta.tipo === "serie") {
    try {
      detalle = await cargarDetalle(ruta.serie.id);
    } catch (e) {
      detalle = null;
    }
    if (id !== estado.renderId) return; // el usuario navegó mientras se cargaba
    cuerpo = detalle ? htmlDetalle(ruta.serie, detalle) : `<p class="error">No se pudo cargar esta serie. <a href="#/${esc(ruta.tema)}">Volver</a></p>`;
  } else if (ruta.tipo === "estado") {
    cuerpo = htmlEstado();
  } else if (ruta.tipo === "home") {
    cuerpo = `${htmlLinea()}${htmlSelectorVista()}<div class="rejilla">${estado.indice.temas.map(htmlTarjetaTema).join("")}</div>${htmlComentarios()}`;
  } else {
    cuerpo = htmlPestana(ruta.tema);
  }
  limpiarGraficos();
  document.getElementById("app").innerHTML = `${htmlEncabezado()}
    <main class="contenedor" id="contenido">${htmlCinta()}${htmlPestanas(ruta.tema)}${cuerpo}</main>${htmlPie()}`;
  document.title = ruta.tipo === "estado" ? "Estado de los datos · Monitor Chile" : ruta.tipo === "serie"
    ? `${ruta.serie.nombre}: ${fmtValor(ruta.serie, ruta.serie.ultimo.valor)} (${ruta.serie.ultimo.etiqueta}) · Monitor Chile`
    : "Monitor Chile · La economía chilena en datos";

  document.querySelectorAll(".mini").forEach((el) => dibujarMini(el, serieDe(el.dataset.serie)));
  if (detalle) activarDetalle(ruta.serie, detalle);
  if (ruta.tipo === "tab") {
    // El salto al gráfico pedido se hace cuando ya se dibujaron todos: antes, las alturas aún no estaban fijadas.
    if (ruta.tema === "comparador") activarComparador(id, ruta.query);
    Promise.all([activarCompuestos(id), activarRevisiones(id)]).then(() => {
      if (ruta.grafico && id === estado.renderId) document.getElementById(`g-${ruta.grafico}`)?.scrollIntoView({ block: "start" });
    });
  }
  document.getElementById("cambiar-tema").addEventListener("click", cambiarTema);
  activarBuscador();
  document.querySelectorAll(".vistas button").forEach((b) =>
    b.addEventListener("click", () => {
      estado.vista = b.dataset.vista;
      try { localStorage.setItem("monitor-vista", estado.vista); } catch (e) { /* solo vale en esta visita */ }
      render();
    })
  );
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
  try {
    const v = localStorage.getItem("monitor-vista");
    if (VISTAS.some(([id]) => id === v)) estado.vista = v;
  } catch (e) { /* sin almacenamiento */ }
  document.addEventListener("keydown", (e) => {
    const escribiendo = /^(input|textarea|select)$/i.test(document.activeElement?.tagName || "");
    if (e.key === "/" && !escribiendo && !e.metaKey && !e.ctrlKey) { e.preventDefault(); document.getElementById("buscar")?.focus(); }
  });
  render();
  window.addEventListener("hashchange", () => render().then(() => { if (!/^#\/[^/]+\/[^/]+/.test(location.hash) || location.hash.startsWith("#/serie/")) window.scrollTo({ top: 0 }); }));
  setInterval(revisarDatosNuevos, INTERVALO_REVISION_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) revisarDatosNuevos(); });
}

iniciar();
