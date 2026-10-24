"""Calendario de publicaciones de EE.UU. para el Monitor: decisiones de la Fed (FOMC) y los principales datos del BLS (IPC, empleo,
IPP) y del BEA (PIB, PCE).

Las fechas son las del calendario oficial de 2026 de cada institución (federalreserve.gov, bls.gov/schedule, bea.gov/news/schedule),
confirmadas en octubre de 2026. OJO: no se calculan con una regla (a diferencia del IMACEC en calendario.py) sino que se copian a mano:
hay que actualizarlas cuando salga el calendario del año siguiente, y algunas fechas de 2026 salieron corridas por el cierre del gobierno
federal de fines de 2025. Fechas de IPP y PCE anteriores a septiembre de 2026 no se verificaron y se omiten (el calendario solo mira el
mes anterior, el actual y el siguiente).

Cada evento: (fecha, tipo, período al que corresponde el dato). El período permite saber si el dato ya está cargado en historico.csv
y qué valor mostrar (el de ese período, no el último disponible).
"""

from datetime import date, timedelta

import pandas as pd

NOMBRES = {
    "fomc": "Decisión de tasas de la Fed (FOMC)",
    "ipc": "IPC (EE.UU., BLS)",
    "empleo": "Empleo y desempleo (EE.UU., BLS)",
    "ipp": "IPP (EE.UU., BLS)",
    "pce": "Gasto de consumo y PCE (EE.UU., BEA)",
    "pib_adelantado": "PIB trimestral, estimación adelantada (EE.UU., BEA)",
    "pib_segundo": "PIB trimestral, segunda estimación (EE.UU., BEA)",
    "pib_tercero": "PIB trimestral, tercera estimación (EE.UU., BEA)",
}

# Tarjeta del Monitor que muestra el dato de cada tipo de evento, y serie de historico.csv que dice si ya está cargado
TARJETA = {
    "fomc": "eeuu_fed_limite_superior", "ipc": "eeuu_inflacion", "empleo": "eeuu_empleo_no_agricola", "ipp": "eeuu_ipp_demanda_final",
    "pce": "eeuu_pce_interanual", "pib_adelantado": "eeuu_pib_trimestral", "pib_segundo": "eeuu_pib_trimestral", "pib_tercero": "eeuu_pib_trimestral",
}
SERIE_DATO = {
    "fomc": "eeuu_fed_limite_superior", "ipc": "eeuu_ipc_indice", "empleo": "eeuu_empleo_no_agricola_nivel", "ipp": "eeuu_ipp_demanda_final_indice",
    "pce": "eeuu_pce_indice", "pib_adelantado": "eeuu_pib_real_anualizado", "pib_segundo": "eeuu_pib_real_anualizado", "pib_tercero": "eeuu_pib_real_anualizado",
}

EVENTOS_2026: list[tuple[str, str, str | None]] = [
    # FOMC: fecha del anuncio (segundo día de la reunión)
    ("2026-01-28", "fomc", None), ("2026-03-18", "fomc", None), ("2026-04-29", "fomc", None), ("2026-06-17", "fomc", None),
    ("2026-07-29", "fomc", None), ("2026-09-16", "fomc", None), ("2026-10-28", "fomc", None), ("2026-12-09", "fomc", None),
    # IPC (BLS): se publica el dato del mes anterior
    ("2026-02-13", "ipc", "2026-01-01"), ("2026-03-11", "ipc", "2026-02-01"), ("2026-04-10", "ipc", "2026-03-01"),
    ("2026-05-12", "ipc", "2026-04-01"), ("2026-06-10", "ipc", "2026-05-01"), ("2026-07-14", "ipc", "2026-06-01"),
    ("2026-08-12", "ipc", "2026-07-01"), ("2026-09-11", "ipc", "2026-08-01"), ("2026-10-14", "ipc", "2026-09-01"),
    ("2026-11-10", "ipc", "2026-10-01"), ("2026-12-10", "ipc", "2026-11-01"),
    # Empleo (BLS, "Employment Situation")
    ("2026-01-09", "empleo", "2025-12-01"), ("2026-02-11", "empleo", "2026-01-01"), ("2026-03-06", "empleo", "2026-02-01"),
    ("2026-04-03", "empleo", "2026-03-01"), ("2026-05-08", "empleo", "2026-04-01"), ("2026-06-05", "empleo", "2026-05-01"),
    ("2026-07-02", "empleo", "2026-06-01"), ("2026-08-07", "empleo", "2026-07-01"), ("2026-09-04", "empleo", "2026-08-01"),
    ("2026-10-02", "empleo", "2026-09-01"), ("2026-11-06", "empleo", "2026-10-01"), ("2026-12-04", "empleo", "2026-11-01"),
    # IPP (BLS), solo las fechas verificadas
    ("2026-09-10", "ipp", "2026-08-01"), ("2026-10-15", "ipp", "2026-09-01"), ("2026-11-13", "ipp", "2026-10-01"), ("2026-12-15", "ipp", "2026-11-01"),
    # PIB (BEA): el período es el trimestre (fecha de su primer día)
    ("2026-04-30", "pib_adelantado", "2026-01-01"), ("2026-05-28", "pib_segundo", "2026-01-01"),
    ("2026-07-30", "pib_adelantado", "2026-04-01"), ("2026-08-26", "pib_segundo", "2026-04-01"), ("2026-09-30", "pib_tercero", "2026-04-01"),
    ("2026-10-29", "pib_adelantado", "2026-07-01"), ("2026-11-25", "pib_segundo", "2026-07-01"), ("2026-12-23", "pib_tercero", "2026-07-01"),
    # PCE (BEA, "Personal Income and Outlays"); varias fechas de 2026 quedaron corridas tras el cierre del gobierno
    ("2026-04-09", "pce", "2026-02-01"), ("2026-05-05", "pce", "2026-03-01"), ("2026-06-09", "pce", "2026-04-01"), ("2026-08-04", "pce", "2026-06-01"),
    ("2026-10-06", "pce", "2026-08-01"), ("2026-10-29", "pce", "2026-09-01"), ("2026-11-25", "pce", "2026-10-01"), ("2026-12-23", "pce", "2026-11-01"),
]


def _cargado(tipo: str, fecha: date, periodo: str | None, historico: pd.DataFrame, hoy: date) -> bool:
    serie = historico[historico["serie"] == SERIE_DATO[tipo]]
    if serie.empty:
        return False
    if tipo == "fomc":  # la nueva tasa rige desde el día siguiente al anuncio y recién ahí aparece en la serie diaria
        return bool(serie["fecha"].max().date() >= fecha + timedelta(days=1))
    if tipo in ("pib_segundo", "pib_tercero"):  # revisan un trimestre que ya estaba cargado: se asume cargado desde el día siguiente
        return fecha < hoy
    return bool((serie["fecha"].dt.date == date.fromisoformat(periodo)).any())


def eventos_eeuu(historico: pd.DataFrame, hoy: date, meses: tuple[tuple[int, int], ...]) -> list[dict]:
    """Eventos de EE.UU. de los (año, mes) pedidos. Mismo formato que los de Chile (ver exportar_monitor.construir_calendario)."""
    salida = []
    for texto_fecha, tipo, periodo in EVENTOS_2026:
        fecha = date.fromisoformat(texto_fecha)
        if (fecha.year, fecha.month) not in meses:
            continue
        cargado = _cargado(tipo, fecha, periodo, historico, hoy)
        if cargado:
            estado = "cargado"
        elif fecha > hoy:
            estado = "pendiente"
        else:
            estado = "hoy" if fecha == hoy else "sin_cargar"
        salida.append({
            "fecha": fecha, "indicador": NOMBRES[tipo], "aproximado": False, "estado": estado, "tipo": tipo,
            "tarjeta": TARJETA[tipo], "periodo": periodo, "pais": "US",
        })
    return salida
