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
