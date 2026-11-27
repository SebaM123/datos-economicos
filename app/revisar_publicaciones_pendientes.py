"""'Portero' del workflow diario de GitHub Actions (actualizar_datos.yml).

El workflow tiene dos tipos de corrida programada:
  - la diaria completa ("0 13 * * *"): trae todas las fuentes, siempre corre.
  - reintentos en días hábiles (CRON_REINTENTO, cada 30 minutos): solo valen la pena cuando el
    INE, el Banco Central o (EE.UU.) el BLS/BEA acaban de publicar algo y el dato todavía no llegó a
    historico.csv. Este script decide eso: si hay una publicación de hoy o de
    los últimos 2 días cuyo dato no está cargado, deja correr; si no, el
    reintento termina de inmediato sin bajar nada. Apenas el dato llega, los
    reintentos se detienen solos.

GitHub no garantiza la hora de los crons y a veces se salta corridas (pasó el 6 y el 27 de noviembre de 2026). Por eso hay un segundo mecanismo:
el «vigía» del workflow de mercado (actualizar_mercado.yml, que corre cada 15 minutos) usa este mismo script con EVENTO=vigia, y si hay algo pendiente
dispara la actualización (workflow_dispatch). Así basta con que cualquiera de las dos programaciones corra para que el dato entre.

Salidas (GITHUB_OUTPUT):
  ejecutar: "true" si el job principal debe correr.
  completa: "true" si además deben bajarse las fuentes secundarias
            (FRED, Banco Mundial, Census); los reintentos solo traen Banco
            Central + mercado.
"""

import os
from datetime import datetime, timedelta, timezone

import pandas as pd

from calendario import hoy_chile, publicaciones_pendientes_de_carga
from calendario_eeuu import eventos_eeuu
from config import HISTORICO_PATH

# Debe ser idéntico al segundo cron de .github/workflows/actualizar_datos.yml (minutos impares: la hora en punto y la media hora son las más congestionadas en GitHub).
CRON_REINTENTO = "7,37 11-22 * * 1-5"
# Los datos de EE.UU. salen a las 8:30 hora de Nueva York (12:30 UTC en verano, 13:30 en invierno): antes de esta hora UTC no tiene sentido buscarlos.
HORA_MIN_EEUU_UTC = (13, 35)
# Tipos de evento de EE.UU. que se detectan por su dato en historico.csv (la decisión de la Fed y las revisiones del PIB no: su «carga» se ve recién al día siguiente).
TIPOS_EEUU = {"ipc", "empleo", "ipp", "pce", "pib_adelantado"}


def pendientes_eeuu(historico: pd.DataFrame, hoy=None, ahora_utc: datetime | None = None, dias_atras: int = 2) -> list[dict]:
    """Publicaciones de EE.UU. de hoy o de los últimos días cuyo dato no está en historico.csv (solo desde la hora de publicación, para hoy)."""
    hoy = hoy or hoy_chile()
    ahora_utc = ahora_utc or datetime.now(timezone.utc)
    desde = hoy - timedelta(days=dias_atras)
    pendientes = []
    meses = tuple(sorted({(desde.year, desde.month), (hoy.year, hoy.month)}))
    for e in eventos_eeuu(historico, hoy, meses):
        if e["tipo"] not in TIPOS_EEUU or e["estado"] == "cargado" or not (desde <= e["fecha"] <= hoy):
            continue
        if e["fecha"] == hoy and (ahora_utc.hour, ahora_utc.minute) < HORA_MIN_EEUU_UTC:
            continue
        pendientes.append(e)
    return pendientes


def decidir(evento: str, cron: str, historico: pd.DataFrame | None, hoy=None, ahora_utc: datetime | None = None) -> tuple[bool, bool, list[dict]]:
    """(ejecutar, completa, pendientes). Los reintentos y el vigía solo corren si hay algo pendiente; si lo pendiente es de EE.UU. la corrida es completa (trae FRED)."""
    es_reintento = (evento == "schedule" and cron == CRON_REINTENTO) or evento == "vigia"
    if not es_reintento:
        return True, True, []
    if historico is None:
        return True, False, []
    chile = publicaciones_pendientes_de_carga(historico, hoy)
    eeuu = pendientes_eeuu(historico, hoy, ahora_utc)
    return bool(chile or eeuu), bool(eeuu), chile + eeuu


def main() -> None:
    evento = os.environ.get("EVENTO", "")
    cron = os.environ.get("CRON", "")
    historico = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"]) if HISTORICO_PATH.exists() else None

    ejecutar, completa, pendientes = decidir(evento, cron, historico)

    print(f"Fecha en Chile: {hoy_chile()} | evento={evento!r} cron={cron!r}")
    if pendientes:
        for p in pendientes:
            print(f"  pendiente de carga: {p['indicador']} (fecha {p['fecha']}, {p['estado']})")
    print(f"ejecutar={ejecutar} completa={completa}")

    salida = os.environ.get("GITHUB_OUTPUT")
    if salida:
        with open(salida, "a", encoding="utf-8") as f:
            f.write(f"ejecutar={'true' if ejecutar else 'false'}\n")
            f.write(f"completa={'true' if completa else 'false'}\n")


if __name__ == "__main__":
    main()
