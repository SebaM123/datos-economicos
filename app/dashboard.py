import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from config import HISTORICO_PATH, NOMBRES_SERIES

TICKERS_EN_VIVO = {
    "IPSA (vía ETF)": "CFMITNIPSA.SN",
    "Dólar (USD/CLP)": "USDCLP=X",
}

st.set_page_config(page_title="Datos Económicos Chile", layout="wide")
st.title("Datos Económicos Chile")


@st.cache_data(ttl=240)
def obtener_cotizacion(ticker: str) -> tuple[float, float] | None:
    historial = yf.Ticker(ticker).history(period="5d")
    if historial.empty or len(historial) < 2:
        return None
    actual = float(historial["Close"].iloc[-1])
    anterior = float(historial["Close"].iloc[-2])
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
            variacion_pct = (actual / anterior - 1) * 100 if anterior else 0
            st.metric(etiqueta, f"{actual:,.2f}", f"{variacion_pct:+.2f}%")
    st.caption("Se actualiza solo cada 5 minutos mientras esta página esté abierta.")


def seccion_historica() -> None:
    st.subheader("Series históricas")

    if not HISTORICO_PATH.exists():
        st.info("Todavía no hay datos históricos acumulados. Corré el pipeline de datos primero.")
        return

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    series_disponibles = [s for s in NOMBRES_SERIES if s in historico["serie"].unique()]

    if not series_disponibles:
        st.info("No hay series reconocidas en historico.csv todavía.")
        return

    for serie in series_disponibles:
        datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
        fig = px.line(
            datos_serie,
            x="fecha",
            y="valor",
            title=NOMBRES_SERIES[serie],
            markers=True,
        )
        fig.update_layout(xaxis_title="", yaxis_title="")
        st.plotly_chart(fig, use_container_width=True)


seccion_en_vivo()
seccion_historica()
