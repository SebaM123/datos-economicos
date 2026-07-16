"""Trae el índice de Gini (desigualdad de ingresos) de Chile y EEUU desde la API
del Banco Mundial (SI.POV.GINI). No requiere API key.

Es una serie anual y con huecos: viene de encuestas de hogares (CASEN en Chile,
Current Population Survey en EEUU), no de un registro administrativo continuo,
así que algunos años no tienen dato.
"""

import requests

from common import append_historico

BASE_URL = "https://api.worldbank.org/v2/country/{pais}/indicator/SI.POV.GINI"

PAISES = {
    "CHL": "chile_gini",
    "USA": "eeuu_gini",
}


def obtener_gini(pais: str, serie: str) -> list[dict]:
    respuesta = requests.get(
        BASE_URL.format(pais=pais),
        params={"format": "json", "per_page": 100},
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json()
    if len(datos) < 2 or not datos[1]:
        return []

    filas = []
    for fila in datos[1]:
        if fila["value"] is None:
            continue
        filas.append({"fecha": f"{fila['date']}-01-01", "serie": serie, "valor": float(fila["value"])})
    return filas


def main() -> None:
    filas = []
    for pais, serie in PAISES.items():
        print(f"Trayendo Gini de {pais}...")
        datos_pais = obtener_gini(pais, serie)
        print(f"  {len(datos_pais)} observaciones")
        filas.extend(datos_pais)

    agregadas = append_historico(filas)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")


if __name__ == "__main__":
    main()
