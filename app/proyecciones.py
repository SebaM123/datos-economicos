"""Proyecciones estadísticas de algunas series clave (hoy: inflación interanual
e IMACEC interanual), para tener una referencia de hacia dónde podrían ir en
los próximos meses.

Importante: esto NO es un pronóstico oficial del Banco Central, del gobierno
ni de nadie — es un modelo estadístico simple (ARIMA) ajustado sobre el
historial de la propia serie, sin usar ninguna otra variable económica. Sirve
como referencia de tendencia, no como predicción certera: por eso siempre se
muestra junto a su intervalo de confianza, que va ensanchándose mes a mes
(cuanto más lejos proyectamos, menos seguros estamos).

Qué es un ARIMA, en criollo: mira los valores pasados de la propia serie (la
parte "AR", autorregresiva) y los errores de predicción pasados (la parte
"MA", promedio móvil) para proyectar los próximos valores. No lleva
componente estacional (la "S" de SARIMA) porque las dos series que usamos acá
ya son variaciones interanuales (% respecto al mismo mes del año pasado), y
esa transformación ya le quita la estacionalidad al dato por construcción —
agregarle un ajuste estacional encima sería redundante.
"""

import warnings

import pandas as pd
import plotly.graph_objects as go
from statsmodels.tsa.arima.model import ARIMA

HORIZONTE_MESES = 6

# order=(p,d,q): autorregresivo de orden 1, una diferenciación, promedio móvil
# de orden 1. Es una elección simple y estándar, no el resultado de una
# búsqueda de "mejor ajuste" — se prefiere así para que el modelo sea fácil
# de explicar y estable de una corrida a otra (no cambia de forma según el
# último dato que llegó).
ORDEN_ARIMA = (1, 1, 1)

# Intervalo de confianza a mostrar (80%: un balance entre informativo y no
# tan ancho que se vuelva inútil visualmente).
ALPHA_INTERVALO = 0.2


def calcular_serie_interanual_ipc(historico: pd.DataFrame) -> pd.DataFrame:
    """Inflación interanual (IPC) para TODO el historial disponible, no solo el
    último dato — a diferencia de series_utils.calcular_inflacion_interanual,
    que da un único número para la tarjeta KPI. Se necesita la serie completa
    como insumo para ajustar el modelo ARIMA.
    """
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha").reset_index(drop=True)
    filas = []
    for i in range(11, len(ipc)):
        ventana = ipc["valor"].iloc[i - 11 : i + 1]
        factor = 1.0
        for valor in ventana:
            factor *= 1 + valor / 100
        filas.append({"fecha": ipc["fecha"].iloc[i], "valor": (factor - 1) * 100})
    return pd.DataFrame(filas)


def calcular_serie_interanual_imacec(historico: pd.DataFrame) -> pd.DataFrame:
    """IMACEC, variación interanual, para todo el historial (ver docstring de
    calcular_serie_interanual_ipc: es lo mismo pero para un índice de nivel
    en vez de una serie de variaciones mensuales).
    """
    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha").reset_index(drop=True)
    filas = []
    for i in range(12, len(imacec)):
        actual = imacec["valor"].iloc[i]
        hace_un_anio = imacec["valor"].iloc[i - 12]
        filas.append({"fecha": imacec["fecha"].iloc[i], "valor": (actual / hace_un_anio - 1) * 100})
    return pd.DataFrame(filas)


def proyectar_serie(datos_serie: pd.DataFrame, horizonte: int = HORIZONTE_MESES) -> pd.DataFrame | None:
    """Ajusta un ARIMA sobre `datos_serie` (columnas fecha/valor, mensual) y
    devuelve las próximas `horizonte` fechas con el valor proyectado y su
    intervalo de confianza. None si no hay historia suficiente para que el
    ajuste tenga sentido (menos de 3 años de datos).
    """
    datos_serie = datos_serie.sort_values("fecha")
    if len(datos_serie) < 36:
        return None

    serie = datos_serie.set_index("fecha")["valor"].asfreq("MS")
    serie = serie.interpolate()  # rellena huecos puntuales; el ARIMA no tolera NaN

    with warnings.catch_warnings():
        # statsmodels avisa de convergencia/especificación en casi cualquier ajuste
        # con datos reales; no son errores, solo ruido para este caso de uso.
        warnings.simplefilter("ignore")
        modelo = ARIMA(serie, order=ORDEN_ARIMA)
        resultado = modelo.fit()

    pronostico = resultado.get_forecast(steps=horizonte)
    intervalo = pronostico.conf_int(alpha=ALPHA_INTERVALO)

    return pd.DataFrame(
        {
            "fecha": pronostico.predicted_mean.index,
            "valor": pronostico.predicted_mean.values,
            "limite_inferior": intervalo.iloc[:, 0].values,
            "limite_superior": intervalo.iloc[:, 1].values,
        }
    )


def construir_figura_proyeccion(historico_serie: pd.DataFrame, proyeccion: pd.DataFrame | None) -> go.Figure:
    """Gráfico compartido entre la versión HTML y la de Streamlit: histórico
    en línea sólida, proyección en línea punteada, banda sombreada para el
    intervalo de confianza.
    """
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=historico_serie["fecha"],
            y=historico_serie["valor"],
            mode="lines",
            name="Histórico",
            line=dict(color="#7c8ff0"),
        )
    )

    if proyeccion is not None and not proyeccion.empty:
        fechas_banda = list(proyeccion["fecha"]) + list(proyeccion["fecha"][::-1])
        valores_banda = list(proyeccion["limite_superior"]) + list(proyeccion["limite_inferior"][::-1])
        fig.add_trace(
            go.Scatter(
                x=fechas_banda,
                y=valores_banda,
                fill="toself",
                fillcolor="rgba(240,169,124,0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                name="Intervalo de confianza (80%)",
                hoverinfo="skip",
            )
        )

        # Se antepone el último punto histórico para que la línea de proyección
        # empiece pegada al histórico, en vez de quedar un salto visual entre las dos.
        ultimo_historico = historico_serie[["fecha", "valor"]].tail(1)
        conexion = pd.concat([ultimo_historico, proyeccion[["fecha", "valor"]]], ignore_index=True)
        fig.add_trace(
            go.Scatter(
                x=conexion["fecha"],
                y=conexion["valor"],
                mode="lines",
                name="Proyección (ARIMA)",
                line=dict(color="#f0a97c", dash="dash"),
            )
        )

    fig.update_layout(
        margin=dict(l=10, r=10, t=10, b=10),
        xaxis_title="",
        yaxis_title="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return fig


# Registro de series proyectables: clave -> (etiqueta, función que arma el
# histórico completo, definición/nota metodológica para el visualizador).
SERIES_PROYECTABLES = {
    "inflacion_interanual": (
        "Inflación interanual (IPC) - histórico y proyección",
        calcular_serie_interanual_ipc,
        "Proyección estadística (ARIMA sobre el historial de la propia serie, sin otras variables), "
        "no es un pronóstico oficial del Banco Central ni de nadie. El área sombreada es el intervalo "
        "de confianza al 80% — mientras más lejos en el tiempo, más ancho (más incertidumbre). "
        "Comparar contra la 'Expectativa inflación 12 meses (EOF)' de la sección Inflación, que es "
        "la expectativa de mercado (encuesta), no un modelo estadístico.",
    ),
    "imacec_interanual": (
        "IMACEC, variación interanual - histórico y proyección",
        calcular_serie_interanual_imacec,
        "Proyección estadística (ARIMA sobre el historial de la propia serie, sin otras variables), "
        "no es un pronóstico oficial de nadie. El área sombreada es el intervalo de confianza al 80% — "
        "mientras más lejos en el tiempo, más ancho (más incertidumbre). No confundir con crecimiento del "
        "PIB anual: esto es la variación de un mes puntual, no un promedio del año. Para la proyección de "
        "PIB que sí incorpora criterio de mercado (no solo el patrón de la propia serie), ver 'Expectativa "
        "PIB' (EEE) en la sección Actividad Económica — ese número, no este gráfico, es la referencia más "
        "confiable si lo que buscás es crecimiento esperado del PIB.",
    ),
}
