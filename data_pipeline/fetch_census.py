"""Trae el índice de Gini por estado de EEUU desde la API del Census Bureau
(American Community Survey, estimaciones de 5 años). Requiere CENSUS_API_KEY
(gratis, registro en https://api.census.gov/data/key_signup.html).

Se guarda aparte en data/gini_por_estado_eeuu.json (foto del último año
disponible, no una serie de tiempo) — mismo patrón que data/pib_por_estado_eeuu.json
(fetch_fred.py), y en un archivo separado en vez de fusionarlo ahí para no acoplar
dos pipelines que corren y pueden fallar de forma independiente.

El Census reporta el Gini en escala 0-1 (ej. 0.48); acá se multiplica por 100
para que quede en la misma escala 0-100 que chile_gini/eeuu_gini (Banco Mundial).
"""

import json
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from fetch_fred import ESTADOS

load_dotenv()

BASE_URL = "https://api.census.gov/data/{anio}/acs/acs5"

SALIDA = Path(__file__).resolve().parent.parent / "data" / "gini_por_estado_eeuu.json"

VARIABLE_GINI = "B19083_001E"

# El Census usa códigos FIPS numéricos, no las abreviaturas de 2 letras que ya
# usamos en fetch_fred.ESTADOS. Se mapea acá para poder cruzar ambos datasets
# por el mismo código de estado.
FIPS_A_CODIGO = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT",
    "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL",
    "18": "IN", "19": "IA", "20": "KS", "21": "KY", "22": "LA", "23": "ME", "24": "MD",
    "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT", "31": "NE",
    "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND",
    "39": "OH", "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA", "54": "WV",
    "55": "WI", "56": "WY",
}


def obtener_gini_por_estado() -> dict:
    key = os.environ.get("CENSUS_API_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno CENSUS_API_KEY.")

    # El ACS de 5 años se publica con rezago; se prueba desde el año más
    # reciente posible hacia atrás hasta encontrar uno ya publicado.
    ultimo_error = None
    for anio in range(date.today().year, date.today().year - 4, -1):
        respuesta = requests.get(
            BASE_URL.format(anio=anio),
            params={"get": f"NAME,{VARIABLE_GINI}", "for": "state:*", "key": key},
            timeout=30,
        )
        if respuesta.status_code == 200:
            filas = respuesta.json()
            resultado = {}
            for nombre, valor, fips in filas[1:]:
                codigo = FIPS_A_CODIGO.get(fips)
                if not codigo or valor is None:
                    continue
                resultado[codigo] = {
                    "nombre": ESTADOS.get(codigo, nombre),
                    "gini": round(float(valor) * 100, 2),
                    "anio": anio,
                }
            return resultado
        ultimo_error = respuesta
    raise RuntimeError(f"No se pudo obtener el ACS de ningún año reciente: {ultimo_error.status_code}")


def main() -> None:
    print("Trayendo índice de Gini por estado (Census Bureau, ACS 5 años)...")
    resultado = obtener_gini_por_estado()
    print(f"  {len(resultado)} estados obtenidos")
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(resultado, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Guardado en {SALIDA}")


if __name__ == "__main__":
    main()
