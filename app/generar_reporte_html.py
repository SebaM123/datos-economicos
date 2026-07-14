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

SALIDA_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"

ESTILO = """
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; background: #0e1117; color: #fafafa; margin: 0; padding: 2rem 3rem 4rem; }
  h1 { font-size: 1.8rem; margin-bottom: 0; }
  .generado { color: #9a9a9a; font-size: 0.9rem; margin-top: 0.25rem; margin-bottom: 2rem; }
  .categoria { margin-top: 3rem; }
  .categoria:first-of-type { margin-top: 0.5rem; }
  .categoria h2 { font-size: 1.3rem; border-bottom: 2px solid #363b4a; padding-bottom: 0.5rem; margin-bottom: 1rem; }
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


def valor_kpi(etiqueta: str, valor: float, fecha_texto: str, sufijo: str = "") -> str:
    return f"""<div class="kpi">
        <div class="etiqueta">{etiqueta}</div>
        <div class="valor">{valor:,.2f}{sufijo}</div>
        <div class="fecha">{fecha_texto}</div>
    </div>"""


def construir_seccion(categoria: dict, historico: pd.DataFrame) -> str:
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

    return f"""<section class="categoria">
        <h2>{categoria['nombre']}</h2>
        <div class="kpis">{"".join(tarjetas)}</div>
        <div class="graficos">{"".join(graficos)}</div>
    </section>"""


def generar() -> None:
    if not HISTORICO_PATH.exists():
        raise RuntimeError("No existe data/historico.csv todavía. Corré el pipeline primero.")

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    ahora = datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M UTC")

    secciones = "".join(construir_seccion(categoria, historico) for categoria in CATEGORIAS)

    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Datos Económicos Chile</title>
{ESTILO}
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
</head>
<body>
<h1>Datos Económicos Chile</h1>
<div class="generado">Generado el {ahora} · se actualiza una vez al día vía GitHub Actions</div>
{secciones}
</body>
</html>"""

    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_PATH.write_text(html, encoding="utf-8")
    print(f"Reporte generado en {SALIDA_PATH}")


if __name__ == "__main__":
    generar()
