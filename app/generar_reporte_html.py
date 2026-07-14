"""Genera un reporte HTML autocontenido a partir de data/historico.csv.

A diferencia del dashboard de Streamlit, este archivo es estático: no se
actualiza solo mientras está abierto, refleja los datos de la última vez
que se generó (cada corrida del pipeline en GitHub Actions lo regenera).
"""

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.io as pio

from config import CATEGORIAS, DEFINICIONES, HISTORICO_PATH, NOMBRES_SERIES
from series_utils import COMPUTADOS, describir_fecha_kpi, insertar_huecos
from ticker import TICKER_ESTILO, construir_ticker_html

SERIES_TICKER = ["ipsa_indice_real", "tipo_cambio", "sp500", "tpm"]

SALIDA_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"

ESTILO = """
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; background: #0e1117; color: #fafafa; margin: 0; padding: 2rem 3rem 4rem; }
  h1 { font-size: 1.8rem; margin-bottom: 0; }
  .generado { color: #9a9a9a; font-size: 0.9rem; margin-top: 0.25rem; margin-bottom: 2rem; }
  details.categoria { margin-top: 1rem; border: 1px solid #262a35; border-radius: 12px; background: #12141b; }
  details.categoria summary {
    font-size: 1.25rem; font-weight: 600; padding: 1.1rem 1.5rem; cursor: pointer;
    list-style: none; display: flex; align-items: center; gap: 0.6rem; user-select: none;
  }
  details.categoria summary::-webkit-details-marker { display: none; }
  details.categoria summary::before { content: "▸"; color: #7c8ff0; transition: transform 0.15s; }
  details.categoria[open] summary::before { transform: rotate(90deg); }
  details.categoria summary:hover { background: #171a24; border-radius: 12px; }
  .categoria-contenido { padding: 0 1.5rem 1.5rem; }
  .kpis { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 1.5rem; }
  .kpi { background: #171923; border: 1px solid #262a35; border-radius: 10px; padding: 1rem 1.5rem; min-width: 180px; }
  .kpi .etiqueta { color: #9a9a9a; font-size: 0.85rem; }
  .kpi .valor { font-size: 1.6rem; font-weight: 600; margin-top: 0.25rem; }
  .kpi .fecha { color: #6b6b6b; font-size: 0.75rem; margin-top: 0.25rem; }
  .graficos { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; }
  .grafico-bloque h3 { font-size: 1rem; margin-bottom: 0; }
  .definicion { color: #9a9a9a; font-size: 0.85rem; margin-top: 0.35rem; margin-bottom: 0; }
  .grafico { margin-top: 0.5rem; }
</style>
"""

# Cada gráfico Plotly se dibuja con las dimensiones que tenga su contenedor en
# ese momento. Si está dentro de un <details> cerrado, arranca con ancho 0 y
# queda roto al abrirlo. Este script lo redibuja bien cada vez que se abre una sección.
SCRIPT_TOGGLE = """
<script>
document.querySelectorAll('details.categoria').forEach(function (det) {
  det.addEventListener('toggle', function () {
    if (det.open) {
      det.querySelectorAll('.js-plotly-plot').forEach(function (el) {
        if (window.Plotly) { window.Plotly.Plots.resize(el); }
      });
    }
  });
});
</script>
"""


def construir_ticker(historico: pd.DataFrame) -> str:
    items = []
    for serie in SERIES_TICKER:
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        if datos_serie.empty:
            continue
        actual = datos_serie["valor"].iloc[-1]
        variacion = None
        if len(datos_serie) >= 2:
            anterior = datos_serie["valor"].iloc[-2]
            if anterior:
                variacion = (actual / anterior - 1) * 100
        items.append((NOMBRES_SERIES[serie], actual, variacion))
    if not items:
        return ""
    return construir_ticker_html(items)


def valor_kpi(etiqueta: str, valor: float, fecha_texto: str, sufijo: str = "") -> str:
    return f"""<div class="kpi">
        <div class="etiqueta">{etiqueta}</div>
        <div class="valor">{valor:,.2f}{sufijo}</div>
        <div class="fecha">{fecha_texto}</div>
    </div>"""


def construir_seccion(categoria: dict, historico: pd.DataFrame, abierta: bool) -> str:
    series_disponibles = [s for s in categoria["series"] if s in historico["serie"].unique()]
    computados_disponibles = [
        (clave, *COMPUTADOS[clave]) for clave in categoria["computados"] if COMPUTADOS[clave][1](historico)
    ]

    if not series_disponibles and not computados_disponibles:
        return ""

    tarjetas = []
    for serie in series_disponibles:
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        ultimo = datos_serie.iloc[-1]
        tarjetas.append(
            valor_kpi(NOMBRES_SERIES[serie], ultimo["valor"], describir_fecha_kpi(serie, ultimo["fecha"]))
        )

    for _, etiqueta_template, funcion in computados_disponibles:
        valor, fecha = funcion(historico)
        etiqueta = etiqueta_template.format(year=fecha.year)
        tarjetas.append(valor_kpi(etiqueta, valor, f"al {fecha.strftime('%d-%m-%Y')}", sufijo="%"))

    graficos = []
    for serie in series_disponibles:
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        datos_grafico = insertar_huecos(datos_serie)
        fig = px.line(datos_grafico, x="fecha", y="valor", markers=True, template="plotly_dark")
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="",
            yaxis_title="",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
        )
        grafico_html = pio.to_html(fig, include_plotlyjs=False, full_html=False)
        definicion = DEFINICIONES.get(serie)
        definicion_html = f"<p class='definicion'>{definicion}</p>" if definicion else ""
        graficos.append(
            f"""<div class="grafico-bloque">
                <h3>{NOMBRES_SERIES[serie]}</h3>
                {definicion_html}
                <div class="grafico">{grafico_html}</div>
            </div>"""
        )

    atributo_open = " open" if abierta else ""
    return f"""<details class="categoria"{atributo_open}>
        <summary>{categoria['nombre']}</summary>
        <div class="categoria-contenido">
            <div class="kpis">{"".join(tarjetas)}</div>
            <div class="graficos">{"".join(graficos)}</div>
        </div>
    </details>"""


def generar() -> None:
    if not HISTORICO_PATH.exists():
        raise RuntimeError("No existe data/historico.csv todavía. Corré el pipeline primero.")

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    ahora = datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M UTC")

    ticker = construir_ticker(historico)
    secciones = "".join(
        construir_seccion(categoria, historico, abierta=(i == 0)) for i, categoria in enumerate(CATEGORIAS)
    )

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Datos Económicos Chile</title>
{ESTILO}
{TICKER_ESTILO}
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
<h1>Datos Económicos Chile</h1>
<div class="generado">Generado el {ahora} · se actualiza una vez al día vía GitHub Actions</div>
{ticker}
{secciones}
{SCRIPT_TOGGLE}
</body>
</html>"""

    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_PATH.write_text(html, encoding="utf-8")
    print(f"Reporte generado en {SALIDA_PATH}")


if __name__ == "__main__":
    generar()
