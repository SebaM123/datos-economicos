"""Trae datos de la Reserva Federal (FRED): PIB total de EEUU y PIB real per
cápita por estado (para comparar cuál estado se parece más a Chile).

El PIB por estado NO usa la misma metodología que el PIB per cápita PPA que
usamos para comparar países (ver config.DEFINICIONES): acá es PIB real en
dólares encadenados, no ajustado por paridad de poder de compra. Sirve como
referencia aproximada, no como comparación exacta.
"""

import json
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

from common import append_historico

load_dotenv()

BASE_URL = "https://api.stlouisfed.org/fred/series/observations"

SALIDA_ESTADOS = Path(__file__).resolve().parent.parent / "data" / "pib_por_estado_eeuu.json"

ESTADOS = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawái", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Luisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Míchigan", "MN": "Minnesota", "MS": "Misisipi", "MO": "Misuri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "Nueva Jersey",
    "NM": "Nuevo México", "NY": "Nueva York", "NC": "Carolina del Norte", "ND": "Dakota del Norte",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregón", "PA": "Pensilvania", "RI": "Rhode Island",
    "SC": "Carolina del Sur", "SD": "Dakota del Sur", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "Virginia Occidental",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "Distrito de Columbia",
}


def _obtener_cliente():
    key = os.environ.get("FRED_API_KEY")
    if not key:
        raise RuntimeError("Falta la variable de entorno FRED_API_KEY.")
    return key


def _ultima_observacion(series_id: str, api_key: str) -> tuple[str, float] | None:
    respuesta = requests.get(
        BASE_URL,
        params={
            "series_id": series_id,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 1,
        },
        timeout=15,
    )
    respuesta.raise_for_status()
    observaciones = respuesta.json().get("observations", [])
    if not observaciones or observaciones[0]["value"] == ".":
        return None
    return observaciones[0]["date"], float(observaciones[0]["value"])


def obtener_pib_total_eeuu(desde: str) -> list[dict]:
    api_key = _obtener_cliente()
    hasta = date.today().isoformat()
    respuesta = requests.get(
        BASE_URL,
        params={
            "series_id": "GDP",
            "api_key": api_key,
            "file_type": "json",
            "observation_start": desde,
            "observation_end": hasta,
        },
        timeout=15,
    )
    respuesta.raise_for_status()
    filas = []
    for obs in respuesta.json().get("observations", []):
        if obs["value"] == ".":
            continue
        filas.append({"fecha": obs["date"], "serie": "eeuu_pib_total", "valor": float(obs["value"])})
    return filas


# Indicadores de EE.UU. para el calendario y las tarjetas del Monitor. FRED los trae el mismo día de la publicación (los de la API del
# Banco Central llegan con semanas de rezago). Se guardan los índices/niveles originales; las variaciones se calculan al exportar.
# (id en historico.csv, código FRED, desde)
INDICADORES_EEUU = [
    ("eeuu_fed_limite_superior", "DFEDTARU", "2015-01-01"),  # tasa objetivo de la Fed, límite superior (diaria)
    ("eeuu_fed_limite_inferior", "DFEDTARL", "2015-01-01"),
    ("eeuu_ipc_indice", "CPIAUCNS", "2010-01-01"),  # IPC sin desestacionalizar: con él se calcula la variación a 12 meses que titula el BLS
    ("eeuu_empleo_no_agricola_nivel", "PAYEMS", "2010-01-01"),  # miles de empleos
    ("eeuu_ipp_demanda_final_indice", "PPIFID", "2010-01-01"),  # IPP de demanda final, el titular del BLS
    ("eeuu_pce_indice", "PCEPI", "2010-01-01"),  # índice de precios del gasto de consumo (el que mira la Fed)
    ("eeuu_pib_real_anualizado", "A191RL1Q225SBEA", "2010-01-01"),  # PIB real, variación trimestral anualizada (%)
]


def obtener_indicadores_eeuu() -> list[dict]:
    api_key = _obtener_cliente()
    filas = []
    for serie, codigo, desde in INDICADORES_EEUU:
        respuesta = requests.get(
            BASE_URL,
            params={"series_id": codigo, "api_key": api_key, "file_type": "json", "observation_start": desde},
            timeout=30,
        )
        respuesta.raise_for_status()
        nuevas = [
            {"fecha": o["date"], "serie": serie, "valor": float(o["value"])}
            for o in respuesta.json().get("observations", [])
            if o["value"] != "."
        ]
        print(f"  {serie}: {len(nuevas)} observaciones")
        filas.extend(nuevas)
    return filas


def obtener_pib_per_capita_por_estado() -> dict:
    api_key = _obtener_cliente()
    resultado = {}
    for codigo, nombre in ESTADOS.items():
        pib = _ultima_observacion(f"{codigo}RGSP", api_key)
        poblacion = _ultima_observacion(f"{codigo}POP", api_key)
        if not pib or not poblacion:
            print(f"Sin datos para {nombre} ({codigo}), se omite.")
            continue
        fecha_pib, valor_pib_millones = pib
        _, valor_poblacion_miles = poblacion
        if valor_poblacion_miles == 0:
            continue
        per_capita = valor_pib_millones * 1000 / valor_poblacion_miles
        resultado[codigo] = {
            "nombre": nombre,
            "pib_per_capita_usd": round(per_capita, 2),
            "anio": fecha_pib[:4],
        }
    return resultado


def main() -> None:
    print("Trayendo indicadores de EEUU (Fed, IPC, empleo, IPP, PCE, PIB)...")
    try:
        agregadas = append_historico(obtener_indicadores_eeuu(), registrar_revisiones=True)
        print(f"  {agregadas} filas nuevas agregadas a historico.csv")
    except Exception as error:  # que falle esto no debe impedir traer el PIB por estado
        print(f"  no se pudieron traer los indicadores de EEUU ({type(error).__name__}: {error})")

    print("Trayendo PIB total de EEUU...")
    filas = obtener_pib_total_eeuu(desde="2010-01-01")
    print(f"  {len(filas)} observaciones")
    agregadas = append_historico(filas, registrar_revisiones=True)
    print(f"  {agregadas} filas nuevas agregadas a historico.csv")

    print("Trayendo PIB per cápita por estado...")
    estados = obtener_pib_per_capita_por_estado()
    print(f"  {len(estados)} estados obtenidos")
    SALIDA_ESTADOS.parent.mkdir(parents=True, exist_ok=True)
    SALIDA_ESTADOS.write_text(json.dumps(estados, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Guardado en {SALIDA_ESTADOS}")


if __name__ == "__main__":
    main()
