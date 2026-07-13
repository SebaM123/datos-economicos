import pandas as pd


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
