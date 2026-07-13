"""Trae series macro del Banco Central (TPM, IPC, desempleo, IMACEC, tipo de cambio)
y las agrega a data/historico.csv.

IMPORTANTE: los códigos de series abajo deben confirmarse corriendo
`python buscar_series.py "<palabra clave>"` una vez que tengas credenciales del BCCh
(ver README.md). Los códigos exactos varían según la metodología/base del INE vigente,
así que no hay que asumirlos de memoria.
"""

from datetime import date, timedelta

from common import append_historico
from credenciales import obtener_cliente

# Códigos confirmados con buscar_series.py contra la API del BCCh.
SERIES = {
    "tpm": "F022.TPM.TIN.D001.NO.Z.D",
    "ipc_variacion_mensual": "F074.IPC.VAR.Z.Z.C.M",
    "desempleo": "F049.DES.TAS.HIST.10.M",
    "imacec": "F032.IMC.IND.Z.Z.EP18.Z.Z.0.M",
    # Expectativas de mercado: Encuesta de Operadores Financieros (EOF).
    "eof_tpm_proxima_reunion": "F089.EOF.TPM.1REU.D",
    "eof_inflacion_12m": "F089.EOF.VII.12MS.D",
    "eof_tipo_cambio_7d": "F089.EOF.TC.7DA.D",
    # Tasas bancarias (colocación/captación) pendientes: los códigos F022.COL.TIP.AN01.NO.Z.D
    # y F022.CAP.TIP.AN01.NO.Z.D dan valores que no calzan con la TPM (ej. 1.76% cuando la
    # TPM estaba en 10.75%), y la API no expone la unidad exacta para confirmarlo. No se
    # agregan hasta verificar qué representan realmente.
}


def obtener_datos(desde: str, hasta: str | None = None) -> list[dict]:
    cliente = obtener_cliente()
    hasta = hasta or date.today().isoformat()

    faltantes = [nombre for nombre, codigo in SERIES.items() if not codigo]
    if faltantes:
        raise RuntimeError(
            "Faltan códigos de serie por confirmar en SERIES: "
            f"{', '.join(faltantes)}. Correr buscar_series.py primero."
        )

    tabla = cliente.cuadro(
        series=list(SERIES.values()),
        nombres=list(SERIES.keys()),
        desde=desde,
        hasta=hasta,
    )

    filas = []
    for fecha, fila in tabla.iterrows():
        for serie in SERIES:
            valor = fila.get(serie)
            if valor is None or valor != valor:  # descarta NaN
                continue
            filas.append({"fecha": fecha.date().isoformat(), "serie": serie, "valor": float(valor)})
    return filas


def main() -> None:
    desde = (date.today() - timedelta(days=45)).isoformat()
    filas = obtener_datos(desde=desde)
    if not filas:
        print("No se obtuvieron datos del BCCh.")
        return
    agregadas = append_historico(filas)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")


if __name__ == "__main__":
    main()
