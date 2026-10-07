import json

import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

from calendario import calendario_del_mes, hoy_chile
from comentarios import COMENTARIOS
from config import (
    CATEGORIAS,
    DEFINICIONES,
    GINI_ESTADOS_PATH,
    HISTORICO_PATH,
    NOMBRES_SERIES,
    OCDE_INDICADORES,
    OCDE_PAISES_PATH,
    PIB_ESTADOS_PATH,
    REVISIONES_PATH,
)
from series_utils import (
    COMPUTADOS,
    SERIES_EXPORTACIONES,
    calcular_anio_movil,
    calcular_contribuciones_imacec,
    calcular_exportaciones_totales_interanual,
    calcular_imacec_tendencia,
    calcular_interanual_generico,
    calcular_interanual_mensual,
    calcular_ipc_componentes_interanual,
    calcular_masa_salarial_real,
    calcular_total_exportaciones,
    calcular_variacion_mensual_serie,
    construir_figura_barras_apiladas,
    construir_figura_barras_variacion,
    construir_figura_contribuciones_imacec,
    construir_figura_lineas,
    construir_figura_ranking_ocde,
    construir_figura_variacion_interanual,
    describir_fecha_kpi,
    estado_mas_parecido_a_chile,
    insertar_huecos,
    obtener_serie,
    resumir_revisiones,
)
from proyecciones import (
    SERIES_PROYECTABLES,
    calcular_serie_interanual_imacec,
    construir_figura_proyeccion,
    proyectar_serie,
)
from ticker import TICKER_ESTILO, construir_ticker_html

MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]

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

    _recargar_si_hay_datos_nuevos()


def _recargar_si_hay_datos_nuevos() -> None:
    """Solo este fragmento se re-ejecuta solo cada 5 min; el resto de la página
    (calendario, tarjetas, gráficos) lee historico.csv una vez al abrir y no lo
    vuelve a mirar. Acá se compara la fecha de modificación del CSV contra la
    que tenía al cargar la página: si el pipeline de GitHub Actions trajo datos
    nuevos, se re-ejecuta la app completa (scope="app"). Se re-renderiza todo
    solo cuando hay un cambio real, no cada 5 minutos.
    """
    if not HISTORICO_PATH.exists():
        return
    modificado = HISTORICO_PATH.stat().st_mtime
    cargado = st.session_state.get("historico_mtime")
    if cargado is None:
        st.session_state["historico_mtime"] = modificado
    elif modificado != cargado:
        st.session_state["historico_mtime"] = modificado
        st.rerun(scope="app")


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


def bloque_anio_movil_desempleo(historico: pd.DataFrame) -> None:
    """Promedio móvil de 12 meses de la tasa de desempleo. A diferencia del año
    móvil de exportaciones (que suma), acá se promedia: sumar una tasa no
    tiene interpretación, promediarla sí sirve para suavizar el ruido mes a mes.
    """
    datos_serie = historico[historico["serie"] == "desempleo"].sort_values("fecha")
    if datos_serie.empty:
        return
    anio_movil = calcular_anio_movil(datos_serie, operacion="mean")
    if anio_movil.empty:
        return

    st.markdown("**Tendencia (promedio móvil 12 meses)**")
    fig = px.line(anio_movil, x="fecha", y="valor", title="Desempleo - promedio móvil 12 meses", markers=False)
    fig.update_layout(xaxis_title="", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Promedio móvil de los últimos 12 meses de la tasa de desempleo, recalculado cada mes. "
        "Suaviza el ruido mes a mes para ver mejor la tendencia de fondo."
    )


def bloque_pib_tendencia(historico: pd.DataFrame) -> None:
    """Crecimiento del PIB vía IMACEC, visto como tendencia (año móvil de 12
    y de 48 meses) y en versión per cápita (dividiendo por la población
    interpolada del Banco Mundial) -- ver
    series_utils.calcular_imacec_tendencia para la metodología completa.
    """
    st.markdown("**Crecimiento del PIB (vía IMACEC): variación interanual, tendencia y per cápita**")
    interanual = calcular_serie_interanual_imacec(historico)
    if not interanual.empty:
        st.plotly_chart(
            construir_figura_variacion_interanual(interanual, "IMACEC - variación interanual (%)"),
            use_container_width=True,
        )
        st.caption(
            "Variación del IMACEC respecto al mismo mes del año anterior, que es la forma habitual de "
            "reportarlo. Verde = la actividad creció, rojo = cayó. Es un proxy mensual del PIB, no el "
            "PIB trimestral oficial. Los gráficos de abajo suavizan este mismo dato para ver la tendencia."
        )
    configuraciones = [
        (12, False, "Año móvil (12 meses), variación interanual"),
        (48, False, "Tendencia larga (48 meses), variación interanual"),
        (12, True, "Año móvil (12 meses) per cápita, variación interanual"),
        (48, True, "Tendencia larga (48 meses) per cápita, variación interanual"),
    ]
    columnas = st.columns(2)
    for i, (ventana, per_capita, titulo) in enumerate(configuraciones):
        datos = calcular_imacec_tendencia(historico, ventana=ventana, per_capita=per_capita)
        if datos.empty:
            continue
        with columnas[i % 2]:
            fig = px.line(datos, x="fecha", y="valor", title=titulo, markers=False)
            fig.update_layout(xaxis_title="", yaxis_title="%")
            st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "El IMACEC se suaviza tomando el promedio de los últimos 12 (o 48) meses en cada fecha "
        "(mismo mecanismo que el 'año móvil' de exportaciones/desempleo), y se grafica la variación "
        "interanual de esa serie ya suavizada -- así se ve la tendencia de fondo del crecimiento, sin "
        "el ruido mes a mes del IMACEC. Las versiones 'per cápita' dividen por la población de Chile "
        "(Banco Mundial, anual, interpolada a mensual) para separar cuánto del crecimiento es más "
        "población de cuánto es más producto por persona. El IMACEC es un proxy mensual del PIB, no "
        "el PIB trimestral oficial."
    )


def bloque_imacec_sectores(historico: pd.DataFrame) -> None:
    """IMACEC abierto por sector: contribución de cada uno al crecimiento (cifras oficiales del
    Banco Central), minero vs no minero, y la serie desestacionalizada (cuya variación mensual
    es como el Banco Central titula el dato)."""
    contribuciones = calcular_contribuciones_imacec(historico)
    if contribuciones.empty:
        return
    st.markdown("**IMACEC por sector: qué explica el crecimiento, minero vs no minero y desestacionalizado**")
    st.plotly_chart(construir_figura_contribuciones_imacec(contribuciones), use_container_width=True)
    st.caption(
        "Cada barra es cuánto aportó (o restó) un sector, en puntos porcentuales, a la variación interanual del "
        "IMACEC; la línea blanca es el total y es la suma de los seis sectores. Fuente: contribuciones publicadas "
        "por el Banco Central (base 2018)."
    )
    columnas = st.columns(2)
    with columnas[0]:
        lineas = {
            "Total": calcular_interanual_mensual(historico, "imacec"),
            "Minero": calcular_interanual_mensual(historico, "imacec_minero"),
            "No minero": calcular_interanual_mensual(historico, "imacec_no_minero"),
        }
        st.plotly_chart(
            construir_figura_lineas(lineas, "IMACEC total, minero y no minero - variación interanual (%)"),
            use_container_width=True,
        )
    with columnas[1]:
        mensual = calcular_variacion_mensual_serie(historico, "imacec_sa")
        if not mensual.empty:
            st.plotly_chart(
                construir_figura_barras_variacion(mensual, "IMACEC desestacionalizado - variación mensual (%)"),
                use_container_width=True,
            )
    niveles = {
        "Total": obtener_serie(historico, "imacec_sa"),
        "Minero": obtener_serie(historico, "imacec_minero_sa"),
        "No minero": obtener_serie(historico, "imacec_no_minero_sa"),
    }
    st.plotly_chart(
        construir_figura_lineas(niveles, "IMACEC desestacionalizado (índice 2018=100)", ytitulo="índice", ventana_inicial=2),
        use_container_width=True,
    )
    st.caption(
        "Desestacionalizado = serie ajustada por el Banco Central para quitar el patrón estacional (ej. el verano o "
        "las fiestas), lo que permite comparar un mes contra el anterior. La variación interanual, en cambio, usa "
        "la serie original: compara cada mes contra el mismo mes del año anterior."
    )


def bloque_masa_salarial(historico: pd.DataFrame) -> None:
    """Masa salarial real: APROXIMACIÓN PROPIA (no es una serie oficial), ver
    series_utils.calcular_masa_salarial_real para la construcción y sus límites."""
    masa = calcular_masa_salarial_real(historico)
    if masa.empty:
        return
    st.markdown("**Masa salarial real (aproximación propia)**")
    tabla = masa.set_index("fecha").rename(
        columns={"aporte_remuneracion": "Remuneración real", "aporte_empleo": "Empleo asalariado", "interanual": "total"}
    )
    st.plotly_chart(
        construir_figura_barras_apiladas(
            tabla, [("Remuneración real", "#6c8cf0"), ("Empleo asalariado", "#e0a83a")],
            "Masa salarial real (aprox.): aporte de la remuneración real y del empleo asalariado (pp)",
            "puntos porcentuales",
        ),
        use_container_width=True,
    )
    lineas = {
        "Remuneración nominal": calcular_interanual_mensual(historico, "remuneraciones_nominal"),
        "Remuneración real": calcular_interanual_mensual(historico, "remuneraciones_real"),
        "Inflación (IPC)": obtener_serie(historico, "ipc_v12"),
    }
    st.plotly_chart(
        construir_figura_lineas(lineas, "Remuneraciones nominales, reales e inflación - variación interanual (%)"),
        use_container_width=True,
    )
    st.caption(
        "No existe una serie oficial de 'masa salarial real': esta es una aproximación propia = índice real de "
        "remuneraciones (INE, por hora) x ocupados asalariados (ENE). Por eso no captura cambios en las horas "
        "trabajadas, y los asalariados incluyen a quienes el índice de remuneraciones podría no cubrir. Sirve para "
        "ver cuánto del movimiento viene del salario real y cuánto del empleo; no como cifra oficial."
    )


def bloque_ipc_componentes(historico: pd.DataFrame) -> None:
    """IPC total vs subyacente y las aperturas analíticas del Banco Central."""
    comp = calcular_ipc_componentes_interanual(historico)
    if comp["IPC total"].empty:
        return
    st.markdown("**Inflación total vs. subyacente y sus componentes (variación interanual)**")
    columnas = st.columns(2)
    with columnas[0]:
        principal = {k: comp[k] for k in ("IPC total", "IPC subyacente (SAE: sin alimentos ni energía)", "IPC sin volátiles")}
        st.plotly_chart(
            construir_figura_lineas(principal, "IPC total y medidas subyacentes - variación interanual (%)", meta=3, ventana_inicial=2),
            use_container_width=True,
        )
    with columnas[1]:
        aperturas = {k: comp[k] for k in ("Bienes sin volátiles", "Servicios sin volátiles", "Volátiles")}
        st.plotly_chart(
            construir_figura_lineas(aperturas, "Bienes, servicios y volátiles - variación interanual (%)", meta=3, ventana_inicial=2),
            use_container_width=True,
        )
    st.caption(
        "El IPC total incluye todo; las medidas subyacentes quitan lo más volátil para ver la tendencia de fondo: SAE "
        "excluye alimentos y energía, 'sin volátiles' excluye además otros componentes de precio muy cambiante "
        "(alimentos frescos, combustibles, etc.). Bienes y servicios sin volátiles permiten ver si la inflación de "
        "fondo viene de los bienes (más ligada al dólar) o de los servicios (más ligada a salarios). La línea "
        "punteada es la meta del Banco Central (3%). Variaciones anuales oficiales del Banco Central/INE."
    )


def seccion_revisiones() -> None:
    """Archivo de valores anteriores que las fuentes oficiales revisaron (ver
    data_pipeline/common.py): para no perder qué se sabía antes de cada revisión."""
    if not REVISIONES_PATH.exists():
        return
    resumen, mayores = resumir_revisiones(pd.read_csv(REVISIONES_PATH), NOMBRES_SERIES)
    if resumen.empty:
        return
    with st.expander("**Revisiones de datos**", expanded=False):
        st.markdown(
            "Las fuentes oficiales (Banco Central, INE) revisan cifras de meses anteriores cada vez que publican. "
            "Los gráficos de arriba usan siempre el valor revisado (el vigente hoy), pero el valor anterior no se "
            "descarta: queda archivado acá con la fecha en que se detectó el cambio."
        )
        st.markdown("**Resumen (últimos 90 días)**")
        st.dataframe(resumen, hide_index=True, use_container_width=True)
        st.markdown("**Los 15 cambios individuales más grandes**")
        st.dataframe(mayores, hide_index=True, use_container_width=True)


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
        if categoria["nombre"] == "Inflación y Política Monetaria":
            bloque_ipc_componentes(historico)
        if categoria["nombre"] == "Empleo":
            bloque_anio_movil_desempleo(historico)
            bloque_masa_salarial(historico)
        if categoria["nombre"] == "Actividad Económica":
            bloque_imacec_sectores(historico)
            bloque_pib_tendencia(historico)


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


def seccion_calendario_y_comentarios(historico: pd.DataFrame) -> None:
    """Calendario de publicaciones económicas del mes en curso (fechas
    oficiales INE/Banco Central, ver calendario.py) y un comentario corto
    y automático de los últimos datos de cada indicador principal (ver
    comentarios.py: son plantillas con lógica fija, no texto generado por
    IA, para que se pueda publicar sin revisión humana cada día).
    """
    hoy = hoy_chile()
    eventos = calendario_del_mes(hoy.year, hoy.month, historico, hoy)

    with st.expander(f"**Calendario y comentario — {MESES_ES[hoy.month - 1]} {hoy.year}**", expanded=True):
        if eventos:
            st.markdown("**Publicaciones del mes**")
            filas = []
            for e in eventos:
                indicador = e["indicador"] + (" *(fecha aprox.)*" if e["aproximado"] else "")
                filas.append({"Día": e["dia"], "Indicador": indicador, "Estado": e["estado"]})
            st.table(pd.DataFrame(filas).set_index("Día"))
            st.caption(
                "Fechas oficiales del INE (IPC, Empleo, IPP) y confirmadas contra notas de prensa "
                "del Banco Central (TPM). IMACEC y PIB trimestral son aproximados: el Banco Central "
                "no publica una lista fija tan clara como el INE, así que se calculan con la regla que "
                "el propio Banco Central aplica en la práctica (ver docstring de calendario.py). "
                "**Estado:** 'publicado y cargado' significa que el dato ya está en este dashboard; "
                "'publicado, aún sin cargar' es el rato entre que el INE/Banco Central publican y que "
                "el pipeline lo baja (corre una vez al día y, los días de publicación, reintenta cada 2 "
                "horas hasta que el dato llega)."
            )

        st.markdown("**Últimos datos, comentados**")
        for clave, (titulo, funcion, _serie) in COMENTARIOS.items():
            texto = funcion(historico)
            if texto:
                st.markdown(f"**{titulo}**: {texto}")
        st.caption(
            "Comentario generado automáticamente con plantillas de texto (no con un modelo de "
            "lenguaje) a partir de los mismos cálculos que las tarjetas de abajo — se actualiza "
            "solo cuando el pipeline diario trae un dato nuevo."
        )


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


def cargar_historico() -> pd.DataFrame | None:
    if not HISTORICO_PATH.exists():
        st.info("Todavía no hay datos históricos acumulados. Corré el pipeline de datos primero.")
        return None
    return pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])


def seccion_historica(historico: pd.DataFrame) -> None:
    for i, categoria in enumerate(CATEGORIAS):
        seccion_categoria(categoria, historico, abierta=(i == 0))


seccion_en_vivo()
historico = cargar_historico()
if historico is not None:
    seccion_calendario_y_comentarios(historico)
    seccion_historica(historico)
    seccion_comercio_exterior(historico)
    seccion_proyecciones(historico)
    seccion_revisiones()
seccion_ocde()
