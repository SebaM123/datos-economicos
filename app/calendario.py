"""Calendario de publicaciones económicas oficiales de Chile (INE y Banco Central).

Fuentes:
- INE: "Calendario 2026, Indicadores de Coyuntura INE" (PDF oficial del INE,
  actualizado el 10 de abril de 2026). Fechas EXACTAS, tomadas directo del
  documento -- hay que actualizar `INE_DIAS_2026` cada año cuando el INE
  publica el calendario del año siguiente (normalmente a fin de año, agenda
  estadística).
- Banco Central, Reuniones de Política Monetaria (RPM): fechas confirmadas
  una por una contra las notas de prensa oficiales de bcentral.cl (el Banco
  Central no publica un único documento tan claro como el del INE). El día
  que se usa es el ÚLTIMO día de cada reunión (2 días, lunes-martes en la
  mayoría de los casos), que es cuando se anuncia la decisión y se actualiza
  la TPM.
- Banco Central, IMACEC: no hay una lista fija publicada con la misma
  claridad -- se usa la regla que el propio Banco Central aplica en la
  práctica (confirmada contra dos publicaciones reales de 2026): el IMACEC
  del mes M se publica el primer día hábil del mes M+2 (ej. IMACEC de junio
  se publica el primer día hábil de agosto).
- Banco Central, PIB trimestral: patrón observado (solo 2 puntos de
  referencia, marcado como aproximado) alrededor del día 18 del segundo mes
  siguiente al cierre del trimestre.

Los cálculos de días hábiles solo excluyen fines de semana -- NO incluyen
feriados chilenos (no hay una fuente simple para eso), así que pueden estar
desfasados 1-2 días alrededor de un feriado. Se marca explícitamente como
aproximado en la UI.
"""

from datetime import date, timedelta

# ---- INE: día exacto de publicación por mes, 2026 (índice 0 = enero) ----
# Cada valor es el día en que se publica el dato del mes ANTERIOR (rezago de
# ~1 mes), tal como lo indica el propio calendario del INE.
INE_DIAS_2026: dict[str, list[int]] = {
    "ipc_variacion_mensual": [8, 6, 6, 8, 8, 8, 8, 7, 8, 8, 6, 7],
    "desempleo": [29, 27, 30, 29, 29, 30, 31, 28, 30, 29, 27, 30],  # Empleo Nacional (ENE), trimestre móvil
    "ipp_general": [23, 24, 24, 24, 22, 24, 24, 24, 24, 23, 24, 24],
}

NOMBRES_PUBLICACION = {
    "ipc_variacion_mensual": "IPC (INE)",
    "desempleo": "Desempleo / ENE (INE)",
    "ipp_general": "IPP (INE)",
    "tpm": "Decisión TPM (Banco Central, RPM)",
    "imacec": "IMACEC (Banco Central)",
    "pib_chile": "PIB trimestral (Banco Central, aprox.)",
}

# ---- Banco Central: Reuniones de Política Monetaria (RPM) 2026 ----
# (mes, día de anuncio -- último día de la reunión). Confirmadas contra
# notas de prensa oficiales, no un solo documento.
BCCH_RPM_2026: list[tuple[int, int]] = [
    (1, 27),
    (3, 24),
    (4, 28),
    (6, 16),
    (7, 28),
    (9, 8),
    (10, 27),
    (12, 15),
]


def _primer_dia_habil(anio: int, mes: int) -> date:
    """Primer día hábil (lunes a viernes) de un mes, sin descontar feriados."""
    d = date(anio, mes, 1)
    while d.weekday() >= 5:  # 5=sabado, 6=domingo
        d += timedelta(days=1)
    return d


def _mes_siguiente(anio: int, mes: int, delta: int) -> tuple[int, int]:
    total = (anio * 12 + (mes - 1)) + delta
    return total // 12, total % 12 + 1


def fecha_imacec(anio: int, mes: int) -> date:
    """Fecha estimada de publicación del IMACEC del mes (anio, mes):
    primer día hábil del mes M+2.
    """
    anio_pub, mes_pub = _mes_siguiente(anio, mes, 2)
    return _primer_dia_habil(anio_pub, mes_pub)


def fecha_pib_trimestral(anio: int, mes_cierre_trimestre: int) -> date:
    """Fecha APROXIMADA de publicación del PIB trimestral cuyo trimestre
    cierra en (anio, mes_cierre_trimestre) -- 3, 6, 9 o 12. Patrón: día 18
    del segundo mes siguiente, ajustado al día hábil más cercano. Solo 2
    puntos de referencia confirmados -- tratar como aproximado.
    """
    anio_pub, mes_pub = _mes_siguiente(anio, mes_cierre_trimestre, 2)
    d = date(anio_pub, mes_pub, 18)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def calendario_del_mes(anio: int, mes: int) -> list[dict]:
    """Devuelve la lista de publicaciones económicas esperadas para un mes
    dado, ordenadas por día. Cada item: {dia, fecha, indicador, fuente,
    aproximado, ya_publicado}.
    """
    hoy = date.today()
    eventos = []

    if anio == 2026:
        for serie, dias in INE_DIAS_2026.items():
            dia = dias[mes - 1]
            fecha = date(anio, mes, dia)
            eventos.append(
                {
                    "fecha": fecha,
                    "indicador": NOMBRES_PUBLICACION[serie],
                    "aproximado": False,
                }
            )
        for mes_rpm, dia_rpm in BCCH_RPM_2026:
            if mes_rpm == mes:
                fecha = date(anio, mes, dia_rpm)
                eventos.append(
                    {
                        "fecha": fecha,
                        "indicador": NOMBRES_PUBLICACION["tpm"],
                        "aproximado": False,
                    }
                )

    anio_origen, mes_origen = _mes_siguiente(anio, mes, -2)
    fecha_im = fecha_imacec(anio_origen, mes_origen)
    if fecha_im.year == anio and fecha_im.month == mes:
        eventos.append(
            {"fecha": fecha_im, "indicador": NOMBRES_PUBLICACION["imacec"], "aproximado": True}
        )

    if mes in (5, 8, 11, 2):  # PIB se publica ~2 meses despues del cierre de trimestre (mar/jun/sep/dic)
        mes_cierre = {5: 3, 8: 6, 11: 9, 2: 12}[mes]
        anio_cierre = anio if mes != 2 else anio - 1
        fecha_pib = fecha_pib_trimestral(anio_cierre, mes_cierre)
        if fecha_pib.year == anio and fecha_pib.month == mes:
            eventos.append(
                {"fecha": fecha_pib, "indicador": NOMBRES_PUBLICACION["pib_chile"], "aproximado": True}
            )

    for e in eventos:
        e["dia"] = e["fecha"].day
        e["ya_publicado"] = e["fecha"] <= hoy

    eventos.sort(key=lambda e: e["fecha"])
    return eventos
