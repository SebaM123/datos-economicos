"""Datos del Comparador del Monitor: indicadores anuales de TODOS los países y de las principales regiones
(Mundo, OCDE, América Latina, Unión Europea...), del Banco Mundial (API pública, sin API key).

Se guarda directo donde la página del Monitor lo lee (docs/monitor/data/comparador/), un archivo por
indicador más la lista de entidades: son datos anuales que cambian una vez al año, así que no tiene
sentido meterlos en historico.csv ni bajarlos cada día (se vuelven a bajar solo si pasaron más de
DIAS_VIGENCIA días; `--forzar` los baja igual).

Los datos del Banco Mundial pueden diferir un poco de las cifras oficiales de Chile (Banco Central/INE),
porque están armonizados para que los países sean comparables entre sí.
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from fetch_worldbank import BASE_URL, _get_con_reintentos

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "comparador"
DIAS_VIGENCIA = 14
ANIO_DESDE = 1990

INDICADORES = {
    "crecimiento_pib": {
        "codigo": "NY.GDP.MKTP.KD.ZG", "nombre": "Crecimiento del PIB", "unidad": "%", "decimales": 1, "promedio": "tasa",
        "descripcion": "Variación anual del PIB real (a precios constantes), en %.",
    },
    "crecimiento_pib_pc": {
        "codigo": "NY.GDP.PCAP.KD.ZG", "nombre": "Crecimiento del PIB per cápita", "unidad": "%", "decimales": 1, "promedio": "tasa",
        "descripcion": "Variación anual del PIB real por habitante, en %: descuenta el efecto de que la población crezca.",
    },
    "inflacion": {
        "codigo": "FP.CPI.TOTL.ZG", "nombre": "Inflación", "unidad": "%", "decimales": 1, "promedio": "nivel",
        "descripcion": "Variación anual del índice de precios al consumidor, en %.",
    },
    "desempleo": {
        "codigo": "SL.UEM.TOTL.ZS", "nombre": "Desempleo", "unidad": "%", "decimales": 1, "promedio": "nivel",
        "descripcion": "Porcentaje de la fuerza de trabajo sin empleo (estimación armonizada de la OIT; no es la tasa que publica el INE).",
    },
}

# Regiones y grupos que se ofrecen en el comparador (el Banco Mundial publica ~80 agregados, la mayoría poco útiles acá).
AGREGADOS = {
    "WLD": "Mundo", "OED": "OCDE (miembros)", "LCN": "América Latina y el Caribe", "EUU": "Unión Europea", "EMU": "Zona del Euro",
    "NAC": "América del Norte", "EAS": "Asia oriental y el Pacífico", "ECS": "Europa y Asia central",
    "MEA": "Oriente Medio, Norte de África, Afganistán y Pakistán", "SAS": "Asia meridional", "SSF": "África subsahariana",
    "HIC": "Países de ingreso alto", "UMC": "Países de ingreso mediano alto", "LMC": "Países de ingreso mediano bajo",
    "LIC": "Países de ingreso bajo",
}


def _json(url: str, params: dict):
    return _get_con_reintentos(url, params=params).json()


def obtener_entidades() -> list[dict]:
    """Países (con su región) y los agregados elegidos, con nombres en español."""
    meta = _json("https://api.worldbank.org/v2/es/country", {"format": "json", "per_page": 400})
    entidades = []
    for e in meta[1]:
        if e["region"]["id"] == "NA":
            continue
        entidades.append({"id": e["id"], "nombre": e["name"].strip(), "tipo": "pais", "region": e["region"]["value"].strip()})
    entidades += [{"id": codigo, "nombre": nombre, "tipo": "agregado", "region": ""} for codigo, nombre in AGREGADOS.items()]
    return entidades


def obtener_indicador(codigo: str, hasta: int) -> dict[str, dict[int, float]]:
    """{entidad: {año: valor}} para todas las entidades, recorriendo las páginas de la API."""
    datos: dict[str, dict[int, float]] = {}
    pagina, paginas = 1, 1
    while pagina <= paginas:
        r = _json(
            BASE_URL.format(pais="all", indicador=codigo),
            {"format": "json", "per_page": 1000, "page": pagina, "date": f"{ANIO_DESDE}:{hasta}"},
        )
        paginas = r[0]["pages"]
        for fila in r[1] or []:
            if fila["value"] is None or not fila["countryiso3code"]:
                continue
            datos.setdefault(fila["countryiso3code"], {})[int(fila["date"])] = float(fila["value"])
        pagina += 1
    return datos


def _vigente() -> bool:
    """¿Están los archivos al día (bajados hace menos de DIAS_VIGENCIA días)?"""
    try:
        fechas = [json.loads((SALIDA / f"{i}.json").read_text(encoding="utf-8"))["descargado"] for i in INDICADORES]
        return all((date.today() - datetime.strptime(f, "%Y-%m-%d").date()).days < DIAS_VIGENCIA for f in fechas)
    except (OSError, KeyError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true", help="bajar los datos aunque los archivos estén vigentes")
    args = parser.parse_args()

    if not args.forzar and _vigente():
        print(f"Comparador: archivos bajados hace menos de {DIAS_VIGENCIA} días, no se vuelve a bajar.")
        return

    entidades = obtener_entidades()
    validas = {e["id"] for e in entidades}
    SALIDA.mkdir(parents=True, exist_ok=True)
    usadas: set[str] = set()
    hasta = date.today().year

    for clave, info in INDICADORES.items():
        print(f"Trayendo {info['nombre']}...")
        datos = {c: serie for c, serie in obtener_indicador(info["codigo"], hasta).items() if c in validas}
        anios = sorted({a for serie in datos.values() for a in serie})
        if not anios:
            raise RuntimeError(f"El Banco Mundial no devolvió datos para {info['codigo']}")
        rango = list(range(anios[0], anios[-1] + 1))
        usadas |= set(datos)
        salida = {
            "id": clave, "nombre": info["nombre"], "unidad": info["unidad"], "decimales": info["decimales"],
            "promedio": info["promedio"], "descripcion": info["descripcion"], "fuente": "Banco Mundial",
            "descargado": date.today().isoformat(), "anios": rango,
            "datos": {c: [round(serie[a], 3) if a in serie else None for a in rango] for c, serie in sorted(datos.items())},
        }
        (SALIDA / f"{clave}.json").write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"  {len(datos)} entidades, {rango[0]}-{rango[-1]}")

    entidades = sorted((e for e in entidades if e["id"] in usadas), key=lambda e: (e["tipo"] != "agregado", e["nombre"]))
    (SALIDA / "entidades.json").write_text(json.dumps(entidades, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Comparador: {len(entidades)} entidades guardadas en {SALIDA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: el comparador sigue con los archivos anteriores
        print(f"Comparador: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
