"""Uso: python buscar_series.py "tasa de politica monetaria"

Busca series disponibles en la API del BCCh cuyo nombre contenga el texto dado,
para encontrar el código exacto que hay que poner en fetch_bcch.py.
"""

import sys

import pandas as pd

from credenciales import obtener_cliente


def main() -> None:
    if len(sys.argv) < 2:
        print('Uso: python buscar_series.py "texto a buscar"')
        sys.exit(1)

    texto = sys.argv[1]
    cliente = obtener_cliente()
    resultados = cliente.buscar(texto)
    with pd.option_context("display.max_rows", None, "display.max_colwidth", 80):
        print(resultados)


if __name__ == "__main__":
    main()
