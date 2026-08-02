import json

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from config import (
    CATEGORIAS,
    DEFINICIONES,
    GINI_ESTADOS_PATH,
    HISTORICO_PATH,
    NOMBRES_SERIES,
    OCDE_INDICADORES,
    OCDE_PAISES_PATH,
    PIB_ESTADOS_PATH,
)
from series_utils import (
    COMPUTADOS,
    SERIES_EXPORTACIONES,
    calcular_anio_movil,
    calcular_exportaciones_totales_interanual,
    calcular_interanual_generico,
    calcular_total_exportaciones,
    construir_figura_ranking_ocde,
    describir_fecha_kpi,
    estado_mas_parecido_a_chile,
    insertar_huecos,
)
from proyecciones import SERIES_PROYECTABLES, construir_figura_proyeccion, proyectar_serie
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


def bloque_gini_estados(historico: pd.DataFrame) -> None:
    """Bloque de referencia (no es una serie de historico.csv): selector con el
    índice de Gini de cada estado de EEUU (Census Bureau, ACS 5 años) y un
    callout con el estado más parecido a Chile en desigualdad.
    """
    if not GINI_ESTADOS_PATH.exists():
        return
    estados = json.loads(GINI_ESTADOS_PATH.read_text(encoding="utf-8"))
    if not estados:
        return

    st.markdown("**Índice de Gini por estado de EEUU**")
    st.caption(
        "Fuente: Census Bureau, estimaciones ACS de 5 años. Mismo concepto que el Gini de Chile/EEUU "
        "de más arriba, pero de una fuente distinta (Census, no Banco Mundial) — sirve para ubicar el "
        "orden de magnitud entre estados, no para una comparación exacta."
    )

    chile = historico[historico["serie"] == "chile_gini"].sort_values("fecha")
    if not chile.empty:
        valor_chile = chile["valor"].iloc[-1]
        anio_chile = chile["fecha"].iloc[-1].year
        cercano = estado_mas_parecido_a_chile(estados, valor_chile, clave_valor="gini")
        if cercano:
            _, datos_cercanos = cercano
            st.info(
                f"El estado de EEUU con Gini más parecido al de Chile es "
                f"**{datos_cercanos['nombre']}** ({datos_cercanos['gini']:.1f}, {datos_cercanos['anio']}) "
                f"— Chile: {valor_chile:.1f} ({anio_chile})."
            )

    opciones = sorted(estados.items(), key=lambda kv: kv[1]["nombre"])
    seleccion = st.selectbox(
        "Elegí un estado",
        options=[codigo for codigo, _ in opciones],
        format_func=lambda codigo: estados[codigo]["nombre"],
        index=None,
        placeholder="Elegí un estado...",
        key="selector_gini_estado",
    )
    if seleccion:
        datos = estados[seleccion]
        st.metric(datos["nombre"], f"{datos['gini']:.1f}")
        st.caption(f"Índice de Gini, {datos['anio']}")


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
        if categoria["nombre"] == "Desigualdad":
            bloque_gini_estados(historico)


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


def seccion_comercio_exterior(historico: pd.DataFrame) -> None:
    """Exportaciones de bienes por sector, con variación interanual (Streamlit
    colorea el delta en verde/rojo automáticamente) para identificar rápido
    qué sector sube o baja en cada actualización.
    """
    series_disponibles = [s for s in SERIES_EXPORTACIONES if s in historico["serie"].unique()]
    if not series_disponibles:
        return

    with st.expander("**Comercio Exterior**", expanded=False):
        tarjetas = []
        total_interanual = calcular_exportaciones_totales_interanual(historico)
        if total_interanual is not None:
            variacion, fecha = total_interanual
            total_actual = calcular_total_exportaciones(historico).iloc[-1]
            tarjetas.append(
                ("Exportaciones totales de bienes", total_actual["valor"], variacion, f"al {fecha.strftime('%d-%m-%Y')}")
            )

        for serie in series_disponibles:
            datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
            ultimo = datos_serie.iloc[-1]
            interanual = calcular_interanual_generico(historico, serie)
            variacion = interanual[0] if interanual else None
            tarjetas.append((NOMBRES_SERIES[serie], ultimo["valor"], variacion, describir_fecha_kpi(serie, ultimo["fecha"])))

        columnas = st.columns(len(tarjetas))
        for columna, (etiqueta, valor, variacion, fecha_texto) in zip(columnas, tarjetas):
            with columna:
                delta = f"{variacion:+.1f}% interanual" if variacion is not None else None
                st.metric(etiqueta, f"US$ {valor:,.0f} MM", delta)
                st.caption(fecha_texto)

        GRAFICOS_POR_FILA = 2
        for inicio in range(0, len(series_disponibles), GRAFICOS_POR_FILA):
            columnas = st.columns(GRAFICOS_POR_FILA)
            for columna, serie in zip(columnas, series_disponibles[inicio : inicio + GRAFICOS_POR_FILA]):
                with columna:
                    datos_completos = historico[historico["serie"] == serie].sort_values("fecha")
                    datos_serie = insertar_huecos(datos_completos)
                    fig = px.line(datos_serie, x="fecha", y="valor", title=NOMBRES_SERIES[serie], markers=True)
                    fig.update_layout(xaxis_title="", yaxis_title="")
                    st.plotly_chart(fig, use_container_width=True)
                    definicion = DEFINICIONES.get(serie)
                    if definicion:
                        st.caption(definicion)

        st.markdown("**Año móvil (tendencia sin estacionalidad)**")
        st.caption(
            "Año móvil: suma de los últimos 12 meses, recalculada cada mes (no solo a fin de año calendario). "
            "Muestra la tendencia de fondo sin los saltos estacionales de los gráficos mensuales de arriba."
        )
        series_anio_movil = [("Exportaciones totales de bienes", calcular_total_exportaciones(historico))]
        for serie in series_disponibles:
            datos_serie = historico[historico["serie"] == serie].sort_values("fecha")
            series_anio_movil.append((NOMBRES_SERIES[serie], datos_serie))

        for inicio in range(0, len(series_anio_movil), GRAFICOS_POR_FILA):
            columnas = st.columns(GRAFICOS_POR_FILA)
            for columna, (etiqueta, datos_serie) in zip(columnas, series_anio_movil[inicio : inicio + GRAFICOS_POR_FILA]):
                with columna:
                    anio_movil = calcular_anio_movil(datos_serie)
                    if anio_movil.empty:
                        continue
                    fig = px.line(anio_movil, x="fecha", y="valor", title=f"{etiqueta} - año móvil", markers=False)
                    fig.update_layout(xaxis_title="", yaxis_title="")
                    st.plotly_chart(fig, use_container_width=True)


def seccion_proyecciones(historico: pd.DataFrame) -> None:
    """Proyección estadística (ARIMA) de algunas series clave. Ver el docstring
    de proyecciones.py para la explicación completa de la metodología.
    """
    with st.expander("**Proyecciones**", expanded=False):
        for etiqueta, funcion_historico, definicion in SERIES_PROYECTABLES.values():
            serie_historica = funcion_historico(historico)
            if serie_historica.empty:
                continue
            proyeccion = proyectar_serie(serie_historica)
            st.markdown(f"**{etiqueta}**")
            fig = construir_figura_proyeccion(serie_historica, proyeccion)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(definicion)


def seccion_ocde() -> None:
    """Sección de referencia (no viene de historico.csv): compara a Chile contra
    el resto de los países de la OCDE en algunos de los indicadores que ya se
    siguen en el resto del dashboard. Ver data_pipeline/fetch_worldbank.py.
    """
    if not OCDE_PAISES_PATH.exists():
        return
    comparacion = json.loads(OCDE_PAISES_PATH.read_text(encoding="utf-8"))
    if not comparacion:
        return

    with st.expander("**Países OCDE**", expanded=False):
        for clave, (titulo, definicion) in OCDE_INDICADORES.items():
            datos_indicador = comparacion.get(clave)
            if not datos_indicador:
                continue
            st.markdown(f"**{titulo}**")
            fig = construir_figura_ranking_ocde(datos_indicador)
            st.plotly_chart(fig, use_container_width=True)
            st.caption(definicion)


def seccion_historica() -> pd.DataFrame | None:
    if not HISTORICO_PATH.exists():
        st.info("Todavía no hay datos históricos acumulados. Corré el pipeline de datos primero.")
        return None

    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    for i, categoria in enumerate(CATEGORIAS):
        seccion_categoria(categoria, historico, abierta=(i == 0))
    return historico


seccion_en_vivo()
historico = seccion_historica()
if historico is not None:
    seccion_comercio_exterior(historico)
    seccion_proyecciones(historico)
seccion_ocde()
