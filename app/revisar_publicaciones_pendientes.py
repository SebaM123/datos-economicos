"""'Portero' del workflow diario de GitHub Actions (actualizar_datos.yml).

El workflow tiene dos tipos de corrida programada:
  - la diaria completa ("0 13 * * *"): trae todas las fuentes, siempre corre.
  - reintentos en días hábiles (CRON_REINTENTO): solo valen la pena cuando el
    INE o el Banco Central acaban de publicar algo y el dato todavía no llegó a
    historico.csv. Este script decide eso: si hay una publicación de hoy o de
    los últimos 2 días cuyo dato no está cargado, deja correr; si no, el
    reintento termina de inmediato sin bajar nada. Apenas el dato llega, los
    reintentos se detienen solos.

Salidas (GITHUB_OUTPUT):
  ejecutar: "true" si el job principal debe correr.
  completa: "true" si además deben bajarse las fuentes secundarias
            (FRED, Banco Mundial, Census); los reintentos solo traen Banco
            Central + mercado.
"""

import os

import pandas as pd

from calendario import hoy_chile, publicaciones_pendientes_de_carga
from config import HISTORICO_PATH

# Debe ser idéntico al segundo cron de .github/workflows/actualizar_datos.yml.
CRON_REINTENTO = "30 12,14,16,18,20,22 * * 1-5"


def decidir(evento: str, cron: str, historico: pd.DataFrame | None, hoy=None) -> tuple[bool, bool, list[dict]]:
    es_reintento = evento == "schedule" and cron == CRON_REINTENTO
    if not es_reintento:
        return True, True, []
    if historico is None:
        return True, False, []
    pendientes = publicaciones_pendientes_de_carga(historico, hoy)
    return bool(pendientes), False, pendientes


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
