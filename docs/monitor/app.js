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
  if (serie.unidad === "pp") return txt + " p.p.";
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
const estado = { meta: null, indice: null, calendario: null, comentarios: null, graficos: [], detalles: {}, renderId: 0, vista: "ultimo" };

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
  Object.assign(estado, { meta, indice, calendario, comentarios, detalles: {} });
}

async function cargarDetalle(id) {
  if (!estado.detalles[id]) estado.detalles[id] = await pedirJSON(`series/${id}.json`, estado.meta.generado);
  return estado.detalles[id];
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

// ---------- Estado de los datos y búsqueda ----------
const norm = (t) => String(t).normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
const diasDesde = (iso) => Math.floor((Date.now() - new Date(iso + "T00:00:00Z").getTime()) / 86400000);

// Las series de las vistas "en el año" / "12 meses" se calculan de otras: contarlas aparte duplicaría los avisos.
function idsDerivados() {
  const base = new Set(estado.indice.temas.flatMap((t) => [t.serie, ...t.secundarias]));
  return new Set(estado.indice.temas.flatMap((t) => Object.values(t.vistas || {})).filter((id) => !base.has(id)));
}
const seriesBase = () => { const d = idsDerivados(); return estado.indice.series.filter((s) => !d.has(s.id)); };
const seriesDemoradas = () => seriesBase().filter((s) => diasDesde(s.ultimo.fecha) > s.max_dias);
const horasDesdeGenerado = () => (Date.now() - new Date(estado.meta.generado).getTime()) / 3600000;
const pipelineAtrasado = () => horasDesdeGenerado() > 72;

function buscar(texto) {
  const tokens = norm(texto).split(/\s+/).filter(Boolean);
  if (!tokens.length) return [];
  const temas = Object.fromEntries(estado.indice.temas.map((t) => [t.id, t.nombre]));
  const resultados = [];
  for (const s of estado.indice.series) {
    const nombre = norm(s.nombre);
    const pajar = `${nombre} ${norm(temas[s.tema] || "")} ${norm(s.fuente)} ${norm(s.definicion || "")}`;
    if (!tokens.every((t) => pajar.includes(t))) continue;
    resultados.push({ s, puntaje: tokens.every((t) => nombre.includes(t)) ? 0 : 1 });
  }
  return resultados.sort((a, b) => a.puntaje - b.puntaje).slice(0, 8).map((r) => r.s);
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
  const ir = (s) => { cerrar(); entrada.value = ""; location.hash = `#/serie/${s.id}`; entrada.blur(); };
  const pintar = () => {
    items = buscar(entrada.value);
    if (!entrada.value.trim()) return cerrar();
    const temas = Object.fromEntries(estado.indice.temas.map((t) => [t.id, t.nombre]));
    lista.innerHTML = items.length
      ? items.map((s, i) => `<li role="option" id="res-${i}" data-i="${i}" aria-selected="false"><span>${esc(s.nombre)}<small>${esc(temas[s.tema] || "")}</small></span><b class="num">${fmtValor(s, s.ultimo.valor)}</b></li>`).join("")
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

function htmlPestanas(ruta) {
  const items = [{ id: "", nombre: "Visión general" }, ...estado.indice.temas.map((t) => ({ id: t.id, nombre: t.nombre }))];
  return `<nav class="pestanas" aria-label="Temas">${items
    .map((t) => `<a class="pestana" href="#/${t.id}" ${t.id === ruta ? 'aria-current="page"' : ""}>${esc(t.nombre)}</a>`)
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
  const temas = Object.fromEntries(estado.indice.temas.map((t) => [t.id, t.nombre]));
  const filas = seriesBase().map((s) => {
    const dias = diasDesde(s.ultimo.fecha);
    return { s, dias, demorada: dias > s.max_dias };
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
          <td class="${demorada ? "tono-igual" : "tono-mejor"}"><b>${demorada ? "Demorada" : "Al día"}</b></td></tr>`).join("")}</tbody>
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
  if (frecuencia === "D") return `${Number(d)} ${MESES[Number(m) - 1]} ${a.slice(2)}`;
  return `${MESES[Number(m) - 1]} ${a.slice(2)}`;
}

function opcionGrande(serie, detalle, anios) {
  const datos = recortar(detalle.datos, anios);
  const valores = datos.map((p) => p[1]);
  const min = Math.min(...valores), max = Math.max(...valores);
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
      formatter: (p) => `${etiquetaFecha(p[0].axisValue, detalle.frecuencia)}<br><b>${fmtValor(detalle, p[0].value)}</b>`,
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
  const tema = estado.indice.temas.find((t) => t.id === serie.tema);
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

// ---------- Render ----------
function rutaActual() {
  const r = location.hash.replace(/^#\/?/, "");
  if (r.startsWith("serie/")) {
    const serie = serieDe(decodeURIComponent(r.slice(6)));
    if (serie) return { tipo: "serie", serie, tema: serie.tema };
  }
  if (r === "estado") return { tipo: "estado", tema: null };
  const tema = estado.indice.temas.some((t) => t.id === r) ? r : "";
  return { tipo: "tema", tema };
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
  } else if (ruta.tema === "") {
    cuerpo = `${htmlLinea()}${htmlSelectorVista()}<div class="rejilla">${estado.indice.temas.map(htmlTarjetaTema).join("")}</div>${htmlComentarios()}`;
  } else {
    const series = estado.indice.series.filter((s) => s.tema === ruta.tema);
    cuerpo = `<div class="rejilla">${series.map(htmlTarjetaSerie).join("")}</div>`;
  }
  limpiarGraficos();
  document.getElementById("app").innerHTML = `${htmlEncabezado()}
    <main class="contenedor" id="contenido">${htmlPestanas(ruta.tema)}${cuerpo}</main>${htmlPie()}`;
  document.title = ruta.tipo === "estado" ? "Estado de los datos · Monitor Chile" : ruta.tipo === "serie"
    ? `${ruta.serie.nombre}: ${fmtValor(ruta.serie, ruta.serie.ultimo.valor)} (${ruta.serie.ultimo.etiqueta}) · Monitor Chile`
    : "Monitor Chile · La economía chilena en datos";

  document.querySelectorAll(".mini").forEach((el) => dibujarMini(el, serieDe(el.dataset.serie)));
  if (detalle) activarDetalle(ruta.serie, detalle);
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
  window.addEventListener("hashchange", () => render().then(() => window.scrollTo({ top: 0 })));
  setInterval(revisarDatosNuevos, INTERVALO_REVISION_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) revisarDatosNuevos(); });
}

iniciar();
