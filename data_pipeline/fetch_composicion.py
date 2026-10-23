"""Composición del PIB de Chile: trae del Banco Central las series para desglosar el PIB por gasto
(consumo, inversión, exportaciones, importaciones), por actividad (sectores) y las exportaciones de bienes
por producto, y las guarda en data/composicion.csv.

Van aparte de historico.csv a propósito: son ~110 series con historia larga (desde 1996 o 2003) que solo
usa el Monitor (pestaña «Composición»). Cada corrida baja todo el historial y reemplaza lo que ya estaba
(las cuentas nacionales se revisan), sin archivar revisiones.

Los códigos de abajo se confirmaron buscando en la API del Banco Central (ver buscar_series.py).
"""

import sys

import pandas as pd

from common import COLUMNS, append_historico, HISTORICO_PATH  # noqa: F401
from credenciales import obtener_cliente

COMPOSICION_PATH = HISTORICO_PATH.parent / "composicion.csv"
DESDE = "1996-01-01"

# --- Cuentas nacionales trimestrales, precios corrientes, series empalmadas referencia 2018 (miles de millones de $)
GASTO = {
    "g_pib": "F032.PIB.FLU.N.CLP.EP18.Z.Z.0.T",
    "g_consumo_privado": "F033.CPR.FLU.N.CLP.EP18.0.T",
    "g_consumo_gobierno": "F033.COG.FLU.N.CLP.EP18.0.T",
    "g_consumo_durables": "F033.CDU.FLU.N.CLP.EP18.0.T",
    "g_consumo_no_durables": "F033.CND.FLU.N.CLP.EP18.0.T",
    "g_consumo_servicios": "F033.CSE.FLU.N.CLP.EP18.0.T",
    "g_fbcf": "F033.FKF.FLU.N.CLP.EP18.0.T",
    "g_fbcf_construccion": "F033.FKK.FLU.N.CLP.EP18.0.T",
    "g_fbcf_maquinaria": "F033.FKO.FLU.N.CLP.EP18.0.T",
    "g_existencias": "F033.VAX.FLU.N.CLP.EP18.0.T",
    "g_exportaciones": "F033.XBS.FLU.N.CLP.EP18.0.T",
    "g_importaciones": "F033.IBS.FLU.N.CLP.EP18.0.T",
}

# --- PIB por actividad (valor agregado) a precios corrientes, sin desestacionalizar
_ACT = "F032.PIB.FLU.N.CLP.EP18.{}.0.T"
ACTIVIDAD = {
    "a_agro": _ACT.format("01.Z"),
    "a_pesca": _ACT.format("02.04"),
    "a_mineria_cobre": _ACT.format("03.05"),
    "a_mineria_otra": _ACT.format("03.06"),
    "a_mineria": _ACT.format("03.Z"),
    "a_ind_alimentos": _ACT.format("04.07"),
    "a_ind_textil": _ACT.format("04.08"),
    "a_ind_madera": _ACT.format("04.09"),
    "a_ind_celulosa": _ACT.format("04.10"),
    "a_ind_quimica": _ACT.format("04.11"),
    "a_ind_minerales": _ACT.format("04.12"),
    "a_ind_metalmecanica": _ACT.format("04.14"),
    "a_industria": _ACT.format("04.Z"),
    "a_ega": _ACT.format("05.Z"),
    "a_construccion": _ACT.format("06.Z"),
    "a_comercio": _ACT.format("07.Z"),
    "a_transporte": _ACT.format("08.19"),
    "a_comunicaciones": _ACT.format("08.20"),
    "a_serv_empresariales": _ACT.format("09.21"),
    "a_vivienda": _ACT.format("10.Z"),
    "a_serv_personales": _ACT.format("11.Z"),
    "a_admin_publica": _ACT.format("12.Z"),
    "a_impuestos": _ACT.format("1415.Z"),
}

# --- Exportaciones de bienes FOB, mensuales (millones de US$): balanza de pagos
_X = "F068.B1.FLU.{}.0.C.N.Z.Z.Z.Z.6.0.M"
CODIGOS_EXPORTACION = [
    "Z", "A", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9",
    "B", "B1", "B11", "B12", "B13", "B14", "B15", "B16", "B17", "B18", "B2", "B21", "B22", "B3", "B4",
    "C", "C1", "C11", "C13", "C14", "C15", "C16", "C17", "C18", "C19", "C1A", "C1B", "C1C", "C1D", "C1E",
    "C2", "C22", "C23", "C24", "C3", "C31", "C32", "C33", "C34", "C35", "C4", "C42", "C43", "C44", "C45",
    "C5", "C51", "C52", "C53", "C53A", "C55", "C56", "C58A", "C58B", "C6", "C61", "C62", "C7", "C71", "C72", "C73", "C9",
]
EXPORTACIONES = {f"x_{codigo}": _X.format(codigo) for codigo in CODIGOS_EXPORTACION}

# Dólar observado diario: para llevar las exportaciones de US$ a pesos y compararlas con el PIB.
TIPO_CAMBIO = "F073.TCO.PRE.Z.D"


def obtener_filas() -> list[dict]:
    cliente = obtener_cliente()
    hasta = pd.Timestamp.today().strftime("%Y-%m-%d")
    series = {**GASTO, **ACTIVIDAD, **EXPORTACIONES}
    tabla = cliente.cuadro(series=list(series.values()), nombres=list(series.keys()), desde=DESDE, hasta=hasta)
    filas = []
    for fecha, fila in tabla.iterrows():
        for nombre in series:
            valor = fila.get(nombre)
            if valor is not None and valor == valor:
                filas.append({"fecha": fecha.date().isoformat(), "serie": nombre, "valor": float(valor)})

    # Promedio mensual del dólar observado (el diario no hace falta guardarlo entero)
    dolar = cliente.cuadro(series=[TIPO_CAMBIO], nombres=["tc"], desde="2003-01-01", hasta=hasta)["tc"].dropna()
    for fecha, valor in dolar.resample("MS").mean().dropna().items():
        filas.append({"fecha": fecha.date().isoformat(), "serie": "tc_promedio_mensual", "valor": float(valor)})
    return filas


def main() -> None:
    filas = obtener_filas()
    if not filas:
        raise RuntimeError("El Banco Central no devolvió datos")
    nuevas = append_historico(filas, csv_path=COMPOSICION_PATH, registrar_revisiones=False)
    print(f"Composición del PIB: {len(filas)} observaciones recibidas, {nuevas} filas nuevas en {COMPOSICION_PATH.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline
        print(f"Composición del PIB: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
