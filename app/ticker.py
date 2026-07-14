"""Cinta de valores que se desplaza de derecha a izquierda (estilo bolsa/Bloomberg),
para usar tanto en el reporte HTML como en el dashboard de Streamlit.
"""

TICKER_ESTILO = """
<style>
  .ticker-wrap {
    overflow: hidden; white-space: nowrap; background: #171923;
    border: 1px solid #262a35; border-radius: 10px; margin-bottom: 1.5rem;
  }
  .ticker-track { display: inline-block; padding: 0.85rem 0; animation: ticker-scroll 35s linear infinite; }
  .ticker-wrap:hover .ticker-track { animation-play-state: paused; }
  .ticker-item { display: inline-block; padding: 0 2.5rem; font-size: 0.95rem; color: #d7d9e0; font-family: -apple-system, Helvetica, Arial, sans-serif; }
  .ticker-item b { color: #7c8ff0; margin-right: 0.4rem; }
  .ticker-up { color: #4ade80; }
  .ticker-down { color: #f87171; }
  @keyframes ticker-scroll {
    0% { transform: translateX(0); }
    100% { transform: translateX(-50%); }
  }
</style>
"""


def construir_ticker_html(items: list[tuple[str, float, float | None]]) -> str:
    """items: lista de (etiqueta, valor, variacion_pct_o_none).
    El contenido se duplica para que el desplazamiento sea un loop continuo,
    sin salto visible cuando vuelve al principio.
    """
    piezas = []
    for etiqueta, valor, variacion in items:
        flecha = ""
        clase = ""
        if variacion is not None:
            if variacion > 0:
                flecha, clase = "▲", "ticker-up"
            elif variacion < 0:
                flecha, clase = "▼", "ticker-down"
            texto_variacion = f' <span class="{clase}">{flecha} {variacion:+.2f}%</span>'
        else:
            texto_variacion = ""
        piezas.append(f'<span class="ticker-item"><b>{etiqueta}</b>{valor:,.2f}{texto_variacion}</span>')

    contenido = "".join(piezas)
    contenido_duplicado = contenido + contenido
    return f'<div class="ticker-wrap"><div class="ticker-track">{contenido_duplicado}</div></div>'
