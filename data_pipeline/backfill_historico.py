"""Carga única: trae el historial completo desde DESDE_DEFAULT hasta hoy,
para todas las series (BCCh + mercado), y lo agrega a data/historico.csv.

Se corre una sola vez (o cuando se quiera extender el historial hacia atrás).
La actualización del día a día la hacen fetch_bcch.py y fetch_market.py.
"""

import fetch_bcch
import fetch_market
import fetch_worldbank
from common import append_historico

DESDE_DEFAULT = "2010-01-01"


def main() -> None:
    print(f"Trayendo historial del BCCh desde {DESDE_DEFAULT}...")
    filas_bcch = fetch_bcch.obtener_datos(desde=DESDE_DEFAULT)
    print(f"  {len(filas_bcch)} observaciones del BCCh")

    print(f"Trayendo historial de mercado desde {DESDE_DEFAULT}...")
    filas_mercado = fetch_market.obtener_historico(desde=DESDE_DEFAULT)
    print(f"  {len(filas_mercado)} observaciones de mercado")

    print("Trayendo historial de Gini (Banco Mundial)...")
    filas_gini = []
    for pais, serie in fetch_worldbank.PAISES.items():
        filas_gini.extend(fetch_worldbank.obtener_gini(pais, serie))
    print(f"  {len(filas_gini)} observaciones de Gini")

    agregadas = append_historico(filas_bcch + filas_mercado + filas_gini)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")


if __name__ == "__main__":
    main()
