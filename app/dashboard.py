import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from config import CATEGORIAS, DEFINICIONES, HISTORICO_PATH, NOMBRES_SERIES
from series_utils import COMPUTADOS, describir_fecha_kpi, insertar_huecos

TICKERS_EN_VIVO = {
    "IPSA (índice real)": "^IPSA",
    "Dólar (USD/CLP)": "USDCLP=X",
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
    columnas = st.columns(len(TICKERS_EN_VIVO))
    for columna, (etiqueta, ticker) in zip(columnas, TICKERS_EN_VIVO.items()):
        datos = obtener_cotizacion(ticker)
        with columna:
            if datos is None:
                st.metric(etiqueta, "sin datos")
                continue
            actual, anterior = datos
            if anterior:
                variacion_pct = (actual / anterior - 1) * 100
                st.metric(etiqueta, f"{actual:,.2f}", f"{variacion_pct:+.2f}%")
            else:
                st.metric(etiqueta, f"{actual:,.2f}")
    st.caption("Se actualiza solo cada 5 minutos mientras esta página esté abierta.")


def seccion_categoria(categoria: dict, historico: pd.DataFrame) -> None:
    series_disponibles = [s for s in categoria["series"] if s in historico["serie"].unique()]
    computados_disponibles = [
        (clave, *COMPUTADOS[clave]) for clave in categoria["computados"] if COMPUTADOS[clave][1](historico)
    ]

    if not series_disponibles and not computados_disponibles:
        return

    st.header(categoria["nombre"])

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
    for categoria in CATEGORIAS:
        seccion_categoria(categoria, historico)


seccion_en_vivo()
seccion_historica()
