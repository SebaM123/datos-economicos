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

from config import HISTORICO_PATH, NOMBRES_SERIES
from series_utils import calcular_inflacion_acumulada_anual, insertar_huecos

SALIDA_PATH = Path(__file__).resolve().parent.parent / "docs" / "index.html"

ESTILO = """
<style>
  body { font-family: -apple-system, Helvetica, Arial, sans-serif; background: #0e1117; color: #fafafa; margin: 0; padding: 2rem 3rem 4rem; }
  h1 { font-size: 1.8rem; margin-bottom: 0; }
  .generado { color: #9a9a9a; font-size: 0.9rem; margin-top: 0.25rem; margin-bottom: 2rem; }
  .kpis { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 2.5rem; }
  .kpi { background: #171923; border: 1px solid #262a35; border-radius: 10px; padding: 1rem 1.5rem; min-width: 180px; }
  .kpi .etiqueta { color: #9a9a9a; font-size: 0.85rem; }
  .kpi .valor { font-size: 1.6rem; font-weight: 600; margin-top: 0.25rem; }
  .kpi .fecha { color: #6b6b6b; font-size: 0.75rem; margin-top: 0.25rem; }
  h2 { font-size: 1.2rem; border-bottom: 1px solid #262a35; padding-bottom: 0.5rem; margin-top: 2.5rem; }
  .grafico { margin-top: 1rem; }
</style>
"""


def construir_kpis(historico: pd.DataFrame) -> str:
    tarjetas = []
    for serie, etiqueta in NOMBRES_SERIES.items():
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        if datos_serie.empty:
            continue
        ultimo = datos_serie.iloc[-1]
        tarjetas.append(
            f"""<div class="kpi">
                <div class="etiqueta">{etiqueta}</div>
                <div class="valor">{ultimo['valor']:,.2f}</div>
                <div class="fecha">al {ultimo['fecha'].strftime('%d-%m-%Y')}</div>
            </div>"""
        )

    inflacion = calcular_inflacion_acumulada_anual(historico)
    if inflacion:
        valor, fecha = inflacion
        tarjetas.append(
            f"""<div class="kpi">
                <div class="etiqueta">Inflación acumulada {fecha.year}</div>
                <div class="valor">{valor:,.2f}%</div>
                <div class="fecha">enero-{fecha.strftime('%b')} {fecha.year}</div>
            </div>"""
        )
    return f'<div class="kpis">{"".join(tarjetas)}</div>'


def construir_graficos(historico: pd.DataFrame) -> str:
    bloques = []
    for serie, etiqueta in NOMBRES_SERIES.items():
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        if datos_serie.empty:
            continue
        datos_serie = insertar_huecos(datos_serie)
        fig = px.line(datos_serie, x="fecha", y="valor", markers=True, template="plotly_dark")
        fig.update_layout(
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="",
            yaxis_title="",
            paper_bgcolor="#0e1117",
            plot_bgcolor="#0e1117",
        )
        grafico_html = pio.to_html(fig, include_plotlyjs=False, full_html=False)
        bloques.append(f"<h2>{etiqueta}</h2><div class='grafico'>{grafico_html}</div>")
    return "".join(bloques)


def generar() -> None:
    if not HISTORICO_PATH.exists():
        raise RuntimeError("No existe data/historico.csv todavía. Corré el pipeline primero.")

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    ahora = datetime.now(timezone.utc).strftime("%d-%m-%Y %H:%M UTC")

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
{construir_kpis(historico)}
{construir_graficos(historico)}
</body>
</html>"""

    SALIDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_PATH.write_text(html, encoding="utf-8")
    print(f"Reporte generado en {SALIDA_PATH}")


if __name__ == "__main__":
    generar()
