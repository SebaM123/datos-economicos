"""Población de Chile por tramos de edad y sexo, 1960-2050, del Banco Mundial (API pública, sin API key).

Los datos son las estimaciones y proyecciones de la División de Población de la ONU (World Population Prospects) que reparte el Banco
Mundial. Se guarda directo donde la pestaña «Población» del Monitor la lee (docs/monitor/data/poblacion.json). Son datos anuales que se
revisan cada dos años, así que se vuelven a bajar solo si pasaron más de DIAS_VIGENCIA días (`--forzar` los baja igual).

OJO: los totales de la ONU no coinciden con los del INE (el Censo 2024 contó 18,48 millones; las proyecciones del INE basadas en el Censo
2017 daban 20,09 millones para 2024 y la ONU 19,76). Las proporciones por edad sí se parecen (Censo 2024: 17,7% menores de 15 años, 68,3% de
15 a 64 y 14,0% de 65 y más). Por eso el Monitor muestra los puntos de los censos al lado de la serie.
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

from fetch_worldbank import BASE_URL, _get_con_reintentos

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "poblacion.json"
DIAS_VIGENCIA = 14
ANIO_DESDE, ANIO_HASTA = 1960, 2050
FUENTE_PROYECCIONES = "40"  # «Population estimates and projections»: llega hasta 2050

TRAMOS = ["0004", "0509", "1014", "1519", "2024", "2529", "3034", "3539", "4044", "4549", "5054", "5559", "6064", "6569", "7074", "7579", "80UP"]
ETIQUETAS = [f"{t[:2].lstrip('0') or '0'}-{t[2:].lstrip('0') or '0'}" if t != "80UP" else "80+" for t in TRAMOS]

# Población censada (total del país). Fuente: INE, censos de población y vivienda.
CENSOS = [(1992, 13348401), (2002, 15116435), (2017, 17574003), (2024, 18480432)]


def _traer(codigo: str) -> dict[int, float]:
    r = _get_con_reintentos(
        BASE_URL.format(pais="CHL", indicador=codigo),
        params={"format": "json", "per_page": 200, "date": f"{ANIO_DESDE}:{ANIO_HASTA}", "source": FUENTE_PROYECCIONES},
    ).json()
    if len(r) < 2 or not r[1]:
        raise RuntimeError(f"El Banco Mundial no devolvió datos para {codigo}")
    return {int(f["date"]): float(f["value"]) for f in r[1] if f["value"] is not None}


def _vigente() -> bool:
    try:
        d = json.loads(SALIDA.read_text(encoding="utf-8"))["descargado"]
        return (date.today() - datetime.strptime(d, "%Y-%m-%d").date()).days < DIAS_VIGENCIA
    except (OSError, KeyError, ValueError):
        return False


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true", help="bajar los datos aunque el archivo esté vigente")
    args = parser.parse_args()
    if not args.forzar and _vigente():
        print(f"Población: archivo bajado hace menos de {DIAS_VIGENCIA} días, no se vuelve a bajar.")
        return

    sexos = {"hombres": "MA", "mujeres": "FE"}
    datos = {s: {t: _traer(f"SP.POP.{t}.{cod}") for t in TRAMOS} for s, cod in sexos.items()}
    anios = sorted(set.intersection(*(set(serie) for s in datos.values() for serie in s.values())))
    salida = {
        "descargado": date.today().isoformat(), "fuente": "ONU (World Population Prospects) vía Banco Mundial", "anios": anios,
        "primer_proyectado": date.today().year, "grupos": ETIQUETAS,
        "hombres": [[round(datos["hombres"][t][a]) for t in TRAMOS] for a in anios],
        "mujeres": [[round(datos["mujeres"][t][a]) for t in TRAMOS] for a in anios],
        "censos": [{"anio": a, "total": n} for a, n in CENSOS],
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Población: {len(anios)} años ({anios[0]}-{anios[-1]}), {len(TRAMOS)} tramos por sexo, guardado en {SALIDA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Población: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
