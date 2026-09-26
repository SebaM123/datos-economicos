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


def calcular_desempleo_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Diferencia interanual de la tasa de desempleo, en puntos porcentuales."""
    return calcular_diferencia_interanual_generico(historico, "desempleo")


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
    "desempleo_interanual": ("Desempleo - variación interanual (puntos porcentuales)", calcular_desempleo_interanual),
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


SERIES_EXPORTACIONES = ["exportaciones_mineria", "exportaciones_agropecuario", "exportaciones_industrial"]


def calcular_interanual_generico(historico: pd.DataFrame, serie: str) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual (12 meses) de una serie mensual cualquiera: compara
    el último dato contra el mismo mes del año anterior, para no confundir
    estacionalidad (ej. la fruta exporta mucho más en verano) con una caída o
    alza real de la actividad.
    """
    datos = historico[historico["serie"] == serie].sort_values("fecha")
    if len(datos) < 13:
        return None
    actual = datos.iloc[-1]
    hace_un_anio = datos.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_total_exportaciones(historico: pd.DataFrame) -> pd.DataFrame:
    """Suma las exportaciones de bienes de los tres sectores (minería, agropecuario-
    silvícola-pesquero, industrial) por fecha. No incluye exportación de servicios.
    """
    disponibles = [s for s in SERIES_EXPORTACIONES if s in historico["serie"].unique()]
    pivote = historico[historico["serie"].isin(disponibles)].pivot(index="fecha", columns="serie", values="valor")
    pivote = pivote.dropna()
    total = pivote.sum(axis=1).reset_index()
    total.columns = ["fecha", "valor"]
    return total


def calcular_exportaciones_totales_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    total = calcular_total_exportaciones(historico)
    if len(total) < 13:
        return None
    actual = total.iloc[-1]
    hace_un_anio = total.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_diferencia_interanual_generico(historico: pd.DataFrame, serie: str) -> tuple[float, pd.Timestamp] | None:
    """Diferencia interanual EN PUNTOS de una serie mensual que ya es una tasa
    o porcentaje (ej. desempleo): valor actual menos el mismo mes del año
    anterior. A diferencia de calcular_interanual_generico (que da un % DE
    CAMBIO, apropiado para niveles/índices), acá tiene más sentido la
    diferencia en puntos — pasar de 8% a 9% de desempleo son "+1 punto",
    no "+12,5%".
    """
    datos = historico[historico["serie"] == serie].sort_values("fecha")
    if len(datos) < 13:
        return None
    actual = datos.iloc[-1]
    hace_un_anio = datos.iloc[-13]
    diferencia = actual["valor"] - hace_un_anio["valor"]
    return diferencia, actual["fecha"]


def calcular_anio_movil(datos_serie: pd.DataFrame, ventana: int = 12, operacion: str = "sum") -> pd.DataFrame:
    """Año móvil: agregado de los últimos `ventana` meses, recalculado en cada
    fecha (no solo a fin de año calendario). `datos_serie` debe venir ordenado
    por fecha, con columnas "fecha" y "valor".

    `operacion="sum"` (por defecto): para series de flujo aditivas y muy
    estacionales (ej. exportaciones en USD) — sumar los últimos 12 meses es
    la forma estándar de ver la tendencia de fondo sin que los picos/valles
    estacionales tapen si en realidad viene subiendo o bajando.

    `operacion="mean"`: para tasas o índices donde sumar 12 meses no tiene
    sentido (ej. tasa de desempleo: sumar da un número sin interpretación,
    promediar sí sirve para suavizar el ruido mes a mes).
    """
    datos_serie = datos_serie.sort_values("fecha")
    resultado = datos_serie[["fecha"]].copy()
    rolling = datos_serie["valor"].rolling(window=ventana)
    resultado["valor"] = rolling.mean() if operacion == "mean" else rolling.sum()
    return resultado.dropna().reset_index(drop=True)


def calcular_variacion_interanual_serie(datos_serie: pd.DataFrame, periodos: int = 12) -> pd.DataFrame:
    """Variación interanual (respecto a `periodos` observaciones atrás) de una
    serie YA agregada -- ej. la salida de calcular_anio_movil -- pensada para
    graficar la evolución completa en el tiempo, no solo el último dato (a
    diferencia de calcular_interanual_generico y afines, que solo devuelven
    el último valor para una tarjeta KPI).
    """
    datos_serie = datos_serie.sort_values("fecha").reset_index(drop=True)
    resultado = datos_serie[["fecha"]].copy()
    resultado["valor"] = (datos_serie["valor"] / datos_serie["valor"].shift(periodos) - 1) * 100
    return resultado.dropna().reset_index(drop=True)


def calcular_poblacion_mensual_interpolada(historico: pd.DataFrame) -> pd.DataFrame:
    """Población de Chile (Banco Mundial, anual) interpolada linealmente a
    frecuencia mensual, para poder dividir series mensuales (ej. IMACEC) por
    población. La población cambia muy poco de un mes a otro, así que
    interpolar linealmente entre los datos anuales es una aproximación
    razonable.

    El Banco Mundial suele publicar el dato del año en curso o del anterior
    (ej. población 2025 ya disponible en 2026), pero para los últimos meses
    de la muestra puede no haber todavía un punto anual posterior con el que
    interpolar -- se extrapolan hasta 2 años hacia adelante usando la tasa de
    crecimiento anual más reciente, para no dejar sin dato justo los meses
    más recientes (los más consultados).
    """
    poblacion = historico[historico["serie"] == "chile_poblacion"].sort_values("fecha")
    if len(poblacion) < 2:
        return pd.DataFrame(columns=["fecha", "valor"])

    serie = poblacion.set_index("fecha")["valor"]
    crecimiento_anual = serie.iloc[-1] / serie.iloc[-2] - 1
    fechas_extra = pd.date_range(serie.index.max() + pd.DateOffset(years=1), periods=2, freq="YS")
    valores_extra = [serie.iloc[-1] * (1 + crecimiento_anual) ** (i + 1) for i in range(len(fechas_extra))]
    serie_extendida = pd.concat([serie, pd.Series(valores_extra, index=fechas_extra)]).sort_index()

    rango_mensual = pd.date_range(serie_extendida.index.min(), serie_extendida.index.max(), freq="MS")
    serie_mensual = (
        serie_extendida.reindex(serie_extendida.index.union(rango_mensual))
        .sort_index()
        .interpolate(method="index")
        .reindex(rango_mensual)
    )
    return serie_mensual.rename("valor").rename_axis("fecha").reset_index()


def calcular_imacec_tendencia(historico: pd.DataFrame, ventana: int, per_capita: bool = False) -> pd.DataFrame:
    """PIB vía IMACEC: variación interanual del "año móvil" (promedio de los
    últimos `ventana` meses), para ver la tendencia de fondo del crecimiento
    sin el ruido mes a mes del IMACEC. `ventana=12` es el año móvil estándar;
    `ventana=48` (4 años) muestra una tendencia de más largo plazo.

    `per_capita=True` divide el IMACEC por la población interpolada
    mensualmente (ver calcular_poblacion_mensual_interpolada) ANTES de
    suavizar, para separar cuánto del crecimiento es "más gente" de cuánto
    es "más producto por persona" -- la comparación clásica entre PIB total
    y PIB per cápita.
    """
    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha")
    if imacec.empty:
        return imacec

    if per_capita:
        poblacion = calcular_poblacion_mensual_interpolada(historico)
        if poblacion.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        combinado = imacec.merge(poblacion, on="fecha", suffixes=("", "_poblacion"))
        if combinado.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        combinado["valor"] = combinado["valor"] / combinado["valor_poblacion"]
        imacec = combinado[["fecha", "valor"]]

    suavizado = calcular_anio_movil(imacec, ventana=ventana, operacion="mean")
    return calcular_variacion_interanual_serie(suavizado)


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
