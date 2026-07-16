"""Trae datos del Banco Mundial (API pública, sin API key):

1. Índice de Gini de Chile y EEUU (histórico, se agrega a historico.csv).
2. Comparación de Chile contra el resto de los países de la OCDE en PIB per
   cápita PPA, desempleo, inflación y Gini (foto del último dato disponible
   por país, se guarda aparte en data/ocde_paises.json — igual que se hizo con
   el PIB por estado de EEUU, para no meter 38 países x 4 indicadores como
   series nuevas en historico.csv).

Los indicadores de la comparación OCDE vienen todos del Banco Mundial para que
sean calculados con la misma metodología entre países, así que pueden diferir
un poco de los datos "oficiales" de Chile/EEUU que se muestran en el resto del
dashboard (que vienen del BCCh/INE/BLS). Por ejemplo, el desempleo acá es una
estimación armonizada de la OIT, no la tasa que publica el INE.
"""

import json
import time
from datetime import date
from pathlib import Path

import requests

from common import append_historico

BASE_URL = "https://api.worldbank.org/v2/country/{pais}/indicator/{indicador}"

SALIDA_OCDE = Path(__file__).resolve().parent.parent / "data" / "ocde_paises.json"

# Índice de Gini de Chile y EEUU, para el historico.csv (ver config.CATEGORIAS, sección Desigualdad).
PAISES_GINI = {
    "CHL": "chile_gini",
    "USA": "eeuu_gini",
}

# Los 38 países miembro de la OCDE (a 2026).
PAISES_OCDE = {
    "AUS": "Australia", "AUT": "Austria", "BEL": "Bélgica", "CAN": "Canadá", "CHL": "Chile",
    "COL": "Colombia", "CRI": "Costa Rica", "CZE": "Chequia", "DNK": "Dinamarca", "EST": "Estonia",
    "FIN": "Finlandia", "FRA": "Francia", "DEU": "Alemania", "GRC": "Grecia", "HUN": "Hungría",
    "ISL": "Islandia", "IRL": "Irlanda", "ISR": "Israel", "ITA": "Italia", "JPN": "Japón",
    "KOR": "Corea del Sur", "LVA": "Letonia", "LTU": "Lituania", "LUX": "Luxemburgo", "MEX": "México",
    "NLD": "Países Bajos", "NZL": "Nueva Zelanda", "NOR": "Noruega", "POL": "Polonia", "PRT": "Portugal",
    "SVK": "Eslovaquia", "SVN": "Eslovenia", "ESP": "España", "SWE": "Suecia", "CHE": "Suiza",
    "TUR": "Turquía", "GBR": "Reino Unido", "USA": "Estados Unidos",
}

INDICADORES_OCDE = {
    "pib_per_capita_ppa": "NY.GDP.PCAP.PP.CD",
    "desempleo": "SL.UEM.TOTL.ZS",
    "inflacion": "FP.CPI.TOTL.ZG",
    "gini": "SI.POV.GINI",
}


def _get_con_reintentos(url: str, params: dict, intentos: int = 3):
    """La API del Banco Mundial a veces tarda o no responde; reintenta antes de fallar."""
    for intento in range(1, intentos + 1):
        try:
            respuesta = requests.get(url, params=params, timeout=30)
            respuesta.raise_for_status()
            return respuesta
        except (requests.exceptions.RequestException,) as error:
            if intento == intentos:
                raise
            print(f"  reintento {intento}/{intentos - 1} tras error: {error}")
            time.sleep(5)


def obtener_gini(pais: str, serie: str) -> list[dict]:
    respuesta = _get_con_reintentos(
        BASE_URL.format(pais=pais, indicador="SI.POV.GINI"),
        params={"format": "json", "per_page": 100},
    )
    datos = respuesta.json()
    if len(datos) < 2 or not datos[1]:
        return []

    filas = []
    for fila in datos[1]:
        if fila["value"] is None:
            continue
        filas.append({"fecha": f"{fila['date']}-01-01", "serie": serie, "valor": float(fila["value"])})
    return filas


def obtener_ultimo_valor_por_pais(indicador: str) -> dict:
    """Para cada país de la OCDE, el último valor disponible del indicador dado.

    Se acota a los últimos años (no hace falta el historial completo para una
    foto del dato más reciente) porque con los 38 países juntos y todo el
    historial, la respuesta no entra en una sola página de la API.
    """
    codigos = ";".join(PAISES_OCDE.keys())
    anio_desde = date.today().year - 8
    respuesta = _get_con_reintentos(
        BASE_URL.format(pais=codigos, indicador=indicador),
        params={"format": "json", "per_page": 2000, "date": f"{anio_desde}:{date.today().year}"},
    )
    datos = respuesta.json()
    if len(datos) < 2 or not datos[1]:
        return {}

    resultado = {}
    for fila in datos[1]:
        codigo = fila["countryiso3code"]
        if codigo not in PAISES_OCDE or fila["value"] is None:
            continue
        anio = int(fila["date"])
        if codigo not in resultado or anio > resultado[codigo]["anio"]:
            resultado[codigo] = {
                "nombre": PAISES_OCDE[codigo],
                "valor": round(float(fila["value"]), 2),
                "anio": anio,
            }
    return resultado


def main() -> None:
    filas = []
    for pais, serie in PAISES_GINI.items():
        print(f"Trayendo Gini de {pais}...")
        datos_pais = obtener_gini(pais, serie)
        print(f"  {len(datos_pais)} observaciones")
        filas.extend(datos_pais)

    agregadas = append_historico(filas)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")

    print("Trayendo comparación OCDE...")
    comparacion = {}
    for clave, indicador in INDICADORES_OCDE.items():
        datos_indicador = obtener_ultimo_valor_por_pais(indicador)
        print(f"  {clave}: {len(datos_indicador)} países")
        comparacion[clave] = datos_indicador

    SALIDA_OCDE.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_OCDE.write_text(json.dumps(comparacion, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Guardado en {SALIDA_OCDE}")


if __name__ == "__main__":
    main()
