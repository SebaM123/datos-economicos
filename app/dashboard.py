import json

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from config import CATEGORIAS, DEFINICIONES, HISTORICO_PATH, NOMBRES_SERIES, PIB_ESTADOS_PATH
from series_utils import COMPUTADOS, describir_fecha_kpi, estado_mas_parecido_a_chile, insertar_huecos
from ticker import TICKER_ESTILO, construir_ticker_html

TICKERS_EN_VIVO = {
    "IPSA (índice real)": "^IPSA",
    "Dólar (USD/CLP)": "USDCLP=X",
    "S&P 500": "^GSPC",
}

st.set_page_config(page_title="Datos Económicos Chile", layout="wide")
st.title("Datos Económicos Chile")


@st.cache_data(ttl=240)
def obtener_cotizacion(ticker: str) -> tuple[float, float | None] | None:
    historial = yf.Ticker(ticker).history(period="5d")
    if historial.empty:
        return None
    actual = float(historial["Close"].iloc[-1])
    anterior = float(historial["Close"].iloc[-2]) if len(historial) >= 2 else None
    return actual, anterior


@st.fragment(run_every="5m")
def seccion_en_vivo() -> None:
    st.subheader("En vivo")

    items_ticker = []
    columnas = st.columns(len(TICKERS_EN_VIVO))
    for columna, (etiqueta, ticker) in zip(columnas, TICKERS_EN_VIVO.items()):
        datos = obtener_cotizacion(ticker)
        with columna:
            if datos is None:
                st.metric(etiqueta, "sin datos")
                continue
            actual, anterior = datos
            variacion_pct = (actual / anterior - 1) * 100 if anterior else None
            if variacion_pct is not None:
                st.metric(etiqueta, f"{actual:,.2f}", f"{variacion_pct:+.2f}%")
            else:
                st.metric(etiqueta, f"{actual:,.2f}")
            items_ticker.append((etiqueta, actual, variacion_pct))

    if items_ticker:
        st.markdown(TICKER_ESTILO + construir_ticker_html(items_ticker), unsafe_allow_html=True)

    st.caption("Se actualiza solo cada 5 minutos mientras esta página esté abierta.")


def bloque_estados_eeuu(historico: pd.DataFrame) -> None:
    """Bloque de referencia (no es una serie de historico.csv): selector con el
    PIB per cápita de cada estado de EEUU y un callout con el estado más
    parecido a Chile, para dar contexto de magnitud a pedido del usuario.
    """
    if not PIB_ESTADOS_PATH.exists():
        return
    estados = json.loads(PIB_ESTADOS_PATH.read_text(encoding="utf-8"))
    if not estados:
        return

    st.markdown("**PIB per cápita por estado de EEUU**")
    st.caption(
        "Referencia aproximada: PIB real por estado en dólares encadenados (fuente FRED), no ajustado "
        "por paridad de poder de compra como el dato de Chile de más arriba — las magnitudes no son "
        "directamente comparables, pero sirven para ubicar el orden de tamaño."
    )

    chile = historico[historico["serie"] == "chile_pib_per_capita_ppa"].sort_values("fecha")
    if not chile.empty:
        valor_chile = chile["valor"].iloc[-1]
        anio_chile = chile["fecha"].iloc[-1].year
        cercano = estado_mas_parecido_a_chile(estados, valor_chile)
        if cercano:
            _, datos_cercanos = cercano
            st.info(
                f"El estado de EEUU con PIB per cápita más parecido al de Chile es "
                f"**{datos_cercanos['nombre']}** (US$ {datos_cercanos['pib_per_capita_usd']:,.0f}, {datos_cercanos['anio']}) "
                f"— Chile: US$ {valor_chile:,.0f} (PPA, {anio_chile})."
            )

    opciones = sorted(estados.items(), key=lambda kv: kv[1]["nombre"])
    seleccion = st.selectbox(
        "Elegí un estado",
        options=[codigo for codigo, _ in opciones],
        format_func=lambda codigo: estados[codigo]["nombre"],
        index=None,
        placeholder="Elegí un estado...",
        key="selector_estado_eeuu",
    )
    if seleccion:
        datos = estados[seleccion]
        st.metric(datos["nombre"], f"US$ {datos['pib_per_capita_usd']:,.0f}")
        st.caption(f"PIB real per cápita, {datos['anio']}")


def seccion_categoria(categoria: dict, historico: pd.DataFrame, abierta: bool) -> None:
    series_disponibles = [s for s in categoria["series"] if s in historico["serie"].unique()]
    computados_disponibles = [
        (clave, *COMPUTADOS[clave]) for clave in categoria["computados"] if COMPUTADOS[clave][1](historico)
    ]

    if not series_disponibles and not computados_disponibles:
        return

    with st.expander(f"**{categoria['nombre']}**", expanded=abierta):
        _contenido_categoria(series_disponibles, computados_disponibles, historico)
        if categoria["nombre"] == "Estados Unidos":
            bloque_estados_eeuu(historico)


def _contenido_categoria(series_disponibles: list[str], computados_disponibles: list, historico: pd.DataFrame) -> None:
    tarjetas = []
    for serie in series_disponibles:
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        ultimo = datos_serie.iloc[-1]
        tarjetas.append((NOMBRES_SERIES[serie], ultimo["valor"], "", describir_fecha_kpi(serie, ultimo["fecha"])))
    for _, etiqueta_template, funcion in computados_disponibles:
        valor, fecha = funcion(historico)
        etiqueta = etiqueta_template.format(year=fecha.year)
        tarjetas.append((etiqueta, valor, "%", f"al {fecha.strftime('%d-%m-%Y')}"))

    KPIS_POR_FILA = 4
    for inicio in range(0, len(tarjetas), KPIS_POR_FILA):
        columnas = st.columns(KPIS_POR_FILA)
        for columna, (etiqueta, valor, sufijo, fecha_texto) in zip(columnas, tarjetas[inicio : inicio + KPIS_POR_FILA]):
            with columna:
                st.metric(etiqueta, f"{valor:,.2f}{sufijo}")
                st.caption(fecha_texto)

    GRAFICOS_POR_FILA = 2
    for inicio in range(0, len(series_disponibles), GRAFICOS_POR_FILA):
        columnas = st.columns(GRAFICOS_POR_FILA)
        for columna, serie in zip(columnas, series_disponibles[inicio : inicio + GRAFICOS_POR_FILA]):
            with columna:
                datos_completos = historico[historico["serie"] == serie].sort_values("fecha")
                datos_serie = insertar_huecos(datos_completos)
                fig = px.line(
                    datos_serie,
                    x="fecha",
                    y="valor",
                    title=NOMBRES_SERIES[serie],
                    markers=True,
                )
                fig.update_layout(xaxis_title="", yaxis_title="")
                st.plotly_chart(fig, use_container_width=True)
                definicion = DEFINICIONES.get(serie)
                if definicion:
                    st.caption(definicion)
                ultimo = datos_completos.iloc[-1]
                st.caption(f"Último dato: {describir_fecha_kpi(serie, ultimo['fecha'])}.")


def seccion_historica() -> None:
    if not HISTORICO_PATH.exists():
        st.info("Todavía no hay datos históricos acumulados. Corré el pipeline de datos primero.")
        return

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    for i, categoria in enumerate(CATEGORIAS):
        seccion_categoria(categoria, historico, abierta=(i == 0))


seccion_en_vivo()
seccion_historica()
