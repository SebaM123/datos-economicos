import pandas as pd


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
