"""Mercado laboral de Chile por sexo y tramo de edad, y ocupados por rama de actividad (INE, Encuesta Nacional de Empleo, vía Banco Central).

Se guarda directo donde la pestaña «Mercado laboral» del Monitor lo lee (docs/monitor/data/laboral.json), igual que el Comparador y la
Población: son ~150 series mensuales (trimestres móviles, miles de personas, serie original) que solo usa esa pestaña, así que no van a
historico.csv. Cada corrida baja todo el historial y reemplaza el archivo (el INE revisa cifras cuando actualiza sus proyecciones de población).

Códigos del Banco Central (familia F049): {medida}.PMT.INE9.{H|M}{edad}.M con medida POB (población en edad de trabajar), FTR (fuerza de
trabajo), OCU (ocupados), DES (desocupados) y FFT (fuera de la fuerza de trabajo, o inactivos); y OCU.PMT.INE4.{rama}.M (ocupados por rama,
CIIU Rev.4, desde 2013) y OCU.PMT.INE9.{85..89}.M (ocupados por categoría ocupacional). Se comprueba que las identidades contables cuadren (POB = FTR + FFT; FTR = OCU + DES) antes de guardar.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from credenciales import obtener_cliente

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "laboral.json"
DESDE = "2010-01-01"
EDADES = ["15", "20", "25", "30", "35", "40", "45", "50", "55", "60", "65", "70"]
ETIQUETAS_EDAD = ["15-19", "20-24", "25-29", "30-34", "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65-69", "70+"]
MEDIDAS = ["POB", "FTR", "OCU", "DES", "FFT"]
SEXOS = {"H": "hombres", "M": "mujeres"}
TOTALES = {"OCU": "F049.OCU.PMT.INE9.01.M", "FTR": "F049.FTR.PMT.INE9.01.M", "DES": "F049.DES.PMT.INE9.01.M", "FFT": "F049.INC.PMT.INE9.01.M"}

# Ocupados por rama de actividad (CIIU Rev.4, Encuesta Nacional de Empleo). El código es lo que sigue a OCU.PMT.INE4.
RAMAS = {
    "31": "Agricultura y pesca", "32": "Minería", "33": "Industria manufacturera",
    "34": "Electricidad y gas", "34A": "Agua y desechos", "35": "Construcción", "36A": "Comercio",
    "36B": "Alojamiento y comidas", "37": "Transporte y almacenamiento", "37A": "Información y comunicaciones",
    "38": "Finanzas y seguros", "39A": "Inmobiliarias", "39B": "Administración pública",
    "39C": "Enseñanza", "39D": "Salud y asistencia social", "39E": "Otros servicios", "39F": "Hogares como empleadores",
    "39G": "Org. extraterritoriales", "39H": "Servicios profesionales",
    "39I": "Servicios administrativos", "39J": "Artes y recreación",
}


# Ocupados según su situación en el empleo (categoría ocupacional, CISE): las cinco suman el total de ocupados.
CATEGORIAS = {"85": "Empleadores", "86": "Cuenta propia", "87": "Asalariados", "88": "Personal de servicio doméstico", "89": "Familiar no remunerado"}


def main() -> None:
    cliente = obtener_cliente()
    hasta = date.today().isoformat()

    codigos = {f"{m}_{s}{e}": f"F049.{m}.PMT.INE9.{s}{e}.M" for m in MEDIDAS for s in SEXOS for e in EDADES}
    codigos.update({f"{m}_T": c for m, c in TOTALES.items()})
    tabla = cliente.cuadro(series=list(codigos.values()), nombres=list(codigos.keys()), desde=DESDE, hasta=hasta).dropna(how="any")
    if tabla.empty:
        raise RuntimeError("El Banco Central no devolvió datos del mercado laboral")

    # Identidades contables: si no cuadran, algo cambió en las series y es mejor no publicar.
    suma = lambda m: sum(tabla[f"{m}_{s}{e}"] for s in SEXOS for e in EDADES)  # noqa: E731
    for m in ("OCU", "FTR", "DES", "FFT"):
        if ((suma(m) - tabla[f"{m}_T"]).abs() > 0.5).any():
            raise RuntimeError(f"Los tramos de edad de {m} no suman el total nacional")
    if ((suma("POB") - suma("FTR") - suma("FFT")).abs() > 0.5).any() or ((suma("OCU") + suma("DES") - suma("FTR")).abs() > 0.5).any():
        raise RuntimeError("No cuadran las identidades POB = FTR + FFT o FTR = OCU + DES")

    salida = {
        "descargado": date.today().isoformat(), "fuente": "INE (Encuesta Nacional de Empleo) vía Banco Central", "edades": ETIQUETAS_EDAD,
        "fechas": [f.strftime("%Y-%m-%d") for f in tabla.index],
        "medidas": {m: {s: [[round(float(v), 1) for v in tabla[f"{m}_{s}{e}"]] for e in EDADES] for s in SEXOS} for m in MEDIDAS},
    }

    ids = {f"INE4.{c}": f"F049.OCU.PMT.INE4.{c}.M" for c in RAMAS}
    ramas = cliente.cuadro(series=list(ids.values()), nombres=list(ids.keys()), desde=DESDE, hasta=hasta).dropna(how="any")
    total = tabla["OCU_T"].reindex(ramas.index)
    salida["ramas"] = {
        "fechas": [f.strftime("%Y-%m-%d") for f in ramas.index],
        "total": [round(float(v), 1) for v in total],
        "series": [{"id": c, "nombre": RAMAS[c], "datos": [round(float(v), 1) for v in ramas[f"INE4.{c}"]]} for c in RAMAS],
    }

    cat_ids = {c: f"F049.OCU.PMT.INE9.{c}.M" for c in CATEGORIAS}
    cats = cliente.cuadro(series=list(cat_ids.values()), nombres=list(cat_ids.keys()), desde=DESDE, hasta=hasta).reindex(tabla.index)
    if cats.isna().any().any() or ((cats.sum(axis=1) - tabla["OCU_T"]).abs() > 0.5).any():
        raise RuntimeError("Las categorías ocupacionales no suman el total de ocupados")
    salida["categorias"] = [{"id": c, "nombre": n, "datos": [round(float(v), 1) for v in cats[c]]} for c, n in CATEGORIAS.items()]

    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Mercado laboral: {len(tabla)} meses ({salida['fechas'][0]} a {salida['fechas'][-1]}), {len(ramas)} meses de ramas, guardado en {SALIDA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Mercado laboral: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
