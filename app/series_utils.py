import pandas as pd
import plotly.graph_objects as go

# Series de expectativas (EOF): el valor de una fecha es el pronóstico que hizo
# el mercado ESE día para un momento futuro, no un dato vigente de esa fecha.
# Acá se define, para cada una, cómo describir el horizonte del pronóstico.
DESCRIPCION_HORIZONTE_EOF = {
    "eof_tpm_proxima_reunion": "para la próxima reunión de política monetaria",
    "eof_inflacion_12m": "para los 12 meses siguientes",
    "eof_tipo_cambio_7d": "para 7 días después",
}


def describir_fecha_kpi(serie: str, fecha: pd.Timestamp) -> str:
    """Texto para mostrar bajo el valor de una tarjeta KPI. Para series de
    expectativas (EOF), aclara que es un pronóstico hecho en esa fecha para
    un momento posterior (que puede ya haber pasado), en vez de dar a entender
    que el dato es vigente a hoy.
    """
    horizonte = DESCRIPCION_HORIZONTE_EOF.get(serie)
    if horizonte:
        return f"pronóstico del {fecha.strftime('%d-%m-%Y')}, {horizonte}"
    return f"al {fecha.strftime('%d-%m-%Y')}"


def calcular_inflacion_acumulada_anual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación acumulada del año calendario en curso: acumula las variaciones
    mensuales del IPC desde enero hasta el último mes disponible con datos.
    Devuelve (valor_porcentual, fecha_del_ultimo_mes_usado), o None si no hay
    ningún dato de IPC para el año en curso todavía.
    """
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha")
    if ipc.empty:
        return None

    anio_actual = pd.Timestamp.now().year
    ipc_anio = ipc[ipc["fecha"].dt.year == anio_actual]
    if ipc_anio.empty:
        return None

    factor = 1.0
    for valor in ipc_anio["valor"]:
        factor *= 1 + valor / 100
    acumulada = (factor - 1) * 100
    return acumulada, ipc_anio["fecha"].iloc[-1]


def calcular_inflacion_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación interanual (12 meses): compone las últimas 12 variaciones
    mensuales del IPC disponibles. Es el dato "titular" que se suele citar
    en medios (distinto de la inflación acumulada del año calendario).
    """
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha")
    if len(ipc) < 12:
        return None

    ultimos_12 = ipc.tail(12)
    factor = 1.0
    for valor in ultimos_12["valor"]:
        factor *= 1 + valor / 100
    interanual = (factor - 1) * 100
    return interanual, ultimos_12["fecha"].iloc[-1]


def calcular_imacec_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación del IMACEC respecto al mismo mes del año anterior (%),
    que es como habitualmente se reporta este indicador (no como índice puro).
    """
    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha")
    if len(imacec) < 13:
        return None

    actual = imacec.iloc[-1]
    hace_un_anio = imacec.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_inflacion_deflactor_pib(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del deflactor del PIB (4 trimestres): una medida
    de inflación alternativa al IPC, que cubre TODO lo que produce el país
    (incluye, por ejemplo, bienes de inversión y exportaciones, no solo lo
    que compran los hogares).
    """
    deflactor = historico[historico["serie"] == "pib_deflactor"].sort_values("fecha")
    if len(deflactor) < 5:
        return None

    actual = deflactor.iloc[-1]
    hace_un_anio = deflactor.iloc[-5]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_inflacion_subyacente_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación interanual del IPC SAE (sin alimentos y energía, "inflación subyacente"):
    compone las últimas 12 variaciones mensuales, igual que la inflación interanual normal
    pero excluyendo los componentes más volátiles. Sirve para ver la tendencia de fondo,
    sin el ruido de precios de combustibles o alimentos frescos.
    """
    ipc_sae = historico[historico["serie"] == "ipc_sae_variacion_mensual"].sort_values("fecha")
    if len(ipc_sae) < 12:
        return None

    ultimos_12 = ipc_sae.tail(12)
    factor = 1.0
    for valor in ultimos_12["valor"]:
        factor *= 1 + valor / 100
    interanual = (factor - 1) * 100
    return interanual, ultimos_12["fecha"].iloc[-1]


def calcular_pib_mineria_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del PIB de minería (mensual, real, desestacionalizado)."""
    pib_mineria = historico[historico["serie"] == "pib_mineria"].sort_values("fecha")
    if len(pib_mineria) < 13:
        return None

    actual = pib_mineria.iloc[-1]
    hace_un_anio = pib_mineria.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_pib_no_minero_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del PIB no minero (trimestral, real, desestacionalizado):
    muestra cómo le va al resto de la economía (servicios, comercio, construcción, etc.)
    sin el efecto del cobre, que puede mover mucho el PIB total por sí solo.
    """
    pib_no_minero = historico[historico["serie"] == "pib_no_minero"].sort_values("fecha")
    if len(pib_no_minero) < 5:
        return None

    actual = pib_no_minero.iloc[-1]
    hace_un_anio = pib_no_minero.iloc[-5]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_tpm_real(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """TPM real ex-post: la tasa de política monetaria menos la inflación
    interanual. Indicador clásico de qué tan restrictiva/expansiva está
    la política monetaria (positivo = restrictiva, negativo = expansiva).
    """
    tpm = historico[historico["serie"] == "tpm"].sort_values("fecha")
    inflacion = calcular_inflacion_interanual(historico)
    if tpm.empty or inflacion is None:
        return None

    tpm_actual = tpm.iloc[-1]
    inflacion_valor, _ = inflacion
    return tpm_actual["valor"] - inflacion_valor, tpm_actual["fecha"]


# Registro de indicadores calculados (no son una serie cruda de historico.csv,
# se derivan de una o más series). "{year}" en la etiqueta se reemplaza por el
# año de la fecha del dato al momento de mostrarlo.
COMPUTADOS = {
    "inflacion_acumulada": ("Inflación acumulada {year}", calcular_inflacion_acumulada_anual),
    "inflacion_interanual": ("Inflación interanual (12 meses, IPC)", calcular_inflacion_interanual),
    "inflacion_deflactor": ("Inflación interanual (deflactor del PIB)", calcular_inflacion_deflactor_pib),
    "inflacion_subyacente_interanual": (
        "Inflación subyacente interanual (IPC SAE, 12 meses)",
        calcular_inflacion_subyacente_interanual,
    ),
    "imacec_interanual": ("IMACEC - variación interanual", calcular_imacec_interanual),
    "tpm_real": ("TPM real ex-post", calcular_tpm_real),
    "pib_mineria_interanual": ("PIB Minería - variación interanual", calcular_pib_mineria_interanual),
    "pib_no_minero_interanual": ("PIB No minero - variación interanual", calcular_pib_no_minero_interanual),
}


def estado_mas_parecido_a_chile(
    estados: dict, valor_chile: float, clave_valor: str = "pib_per_capita_usd"
) -> tuple[str, dict] | None:
    """De los estados de EEUU (ver fetch_fred.py y fetch_census.py), devuelve el
    código y los datos del que tiene el valor más cercano al de Chile en el
    indicador dado (`clave_valor`). Comparación aproximada, no exacta: cada
    indicador tiene su propia nota de metodología en la UI.
    """
    if not estados:
        return None
    return min(estados.items(), key=lambda item: abs(item[1][clave_valor] - valor_chile))


def construir_figura_ranking_ocde(datos_por_pais: dict, pais_destacado: str = "CHL") -> go.Figure:
    """Gráfico de barras horizontal comparando un indicador entre países de la OCDE
    (ver data_pipeline/fetch_worldbank.py), ordenado de menor a mayor, con Chile
    destacado en otro color para ubicarlo rápido entre sus pares.
    """
    filas = sorted(
        ((info["nombre"], info["valor"], codigo, info["anio"]) for codigo, info in datos_por_pais.items()),
        key=lambda fila: fila[1],
    )
    nombres = [fila[0] for fila in filas]
    valores = [fila[1] for fila in filas]
    anios = [fila[3] for fila in filas]
    colores = ["#7c8ff0" if fila[2] == pais_destacado else "#3a3f4f" for fila in filas]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=nombres,
            orientation="h",
            marker_color=colores,
            customdata=anios,
            hovertemplate="%{y}: %{x}<br>Año: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(500, 24 * len(filas)),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def insertar_huecos(datos_serie: pd.DataFrame, umbral_dias: int = 45) -> pd.DataFrame:
    """Inserta filas con valor nulo entre puntos separados por más de
    `umbral_dias`, para que los gráficos de línea corten en vez de unir
    con una recta dos fechas que en realidad no tienen datos entre medio.
    """
    filas = datos_serie.to_dict("records")
    resultado = []
    for i, fila in enumerate(filas):
        if i > 0:
            dias = (fila["fecha"] - filas[i - 1]["fecha"]).days
            if dias > umbral_dias:
                resultado.append({"fecha": filas[i - 1]["fecha"] + pd.Timedelta(days=1), "valor": None})
        resultado.append(fila)
    return pd.DataFrame(resultado)
