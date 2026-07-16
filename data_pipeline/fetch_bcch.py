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
    # Desglose del mercado laboral chileno (Fuerza de trabajo = Ocupados + Desocupados).
    "fuerza_trabajo": "F049.FTR.PMT.INE.10.M",
    "ocupados": "F049.OCU.PMT.INE.10.M",
    "desocupados": "F049.DES.PMT.INE.10.M",
    # Datos de EEUU (ya disponibles en el BCCh, sin fuente nueva). No hay tasa de la Fed
    # en esta API — para eso haría falta otra fuente (ej. FRED).
    "eeuu_desempleo": "F019.DES.TAS.10.M",
    "eeuu_inflacion": "F019.IPC.V12.10.M",
    "eeuu_pib_per_capita": "F019.PIBPC.FLU.US.A",
    # PIB de Chile (nivel trimestral, desestacionalizado) y el índice del deflactor del PIB
    # (para poder calcular una medida de inflación alternativa al IPC).
    "pib_chile": "F032.PIB.FLU.N.CLP.EP18.Z.Z.1.T",
    "pib_deflactor": "F032.PIB.DEF.N.CLP.EP18.Z.Z.0.T",
    # PIB per cápita de Chile, mismo origen (FMI-WEO) y unidad (USD, PPA) que
    # eeuu_pib_per_capita, para que ambos sean directamente comparables. Esta
    # serie incluye proyecciones del FMI hasta 2030; al pedir con hasta=hoy
    # solo se trae el año en curso (que igual es una estimación) hacia atrás.
    "chile_pib_per_capita_ppa": "F012.PPCP.FLU.N.7.AME.CL.USD.FMI.Z.0.A",
    # Índice de precios al productor: Chile (índice, base 2019=100) y EEUU (variación
    # interanual, "todos los commodities" — mismo origen que eeuu_desempleo/eeuu_inflacion).
    "ipp_general": "F075.IPP.IND.P0551.2019.Z.M",
    "eeuu_ipp": "F019.IPP.V12.10.M",
    # PIB por sector: minería (mensual) y no minero (trimestral, series empalmadas), ambos
    # en volumen (términos reales) y desestacionalizados, para ver si la actividad depende
    # del cobre o si el resto de la economía (servicios, etc.) va por otro lado.
    "pib_mineria": "F032.PIB.FLU.R.CLP.2018.03.Z.1.M",
    "pib_no_minero": "F032.PIB.FLU.R.CLP.EP18.N03.Z.1.T",
    # Tasas bancarias (colocación/captación) pendientes: los códigos F022.COL.TIP.AN01.NO.Z.D
    # y F022.CAP.TIP.AN01.NO.Z.D dan valores que no calzan con la TPM (ej. 1.76% cuando la
    # TPM estaba en 10.75%), y la API no expone la unidad exacta para confirmarlo. No se
    # agregan hasta verificar qué representan realmente.
}

# IPC SAE (inflación subyacente, sin alimentos y energía): el BCCh recalcula la serie con
# cada cambio de base (2018=100, 2023=100, etc.) y no mantiene actualizado un empalme
# histórico único como sí hace con el IPC general. Se arma acá el empalme a mano: se usa
# el histórico oficial hasta que corta, y de ahí en adelante la serie de la base vigente
# (que gana en las fechas donde ambas se superponen, por venir después en la lista).
SERIES_IPC_SAE_EMPALME = [
    "F074.IPCSAE.VAR.Z.Z.C.M",  # histórico oficial, hasta 2023-12
    "F074.IPCSAE.VAR.Z.2023.C.M",  # base 2023=100, vigente
]


def obtener_ipc_sae_empalmado(cliente, desde: str, hasta: str) -> list[dict]:
    """Arma la serie de IPC SAE (inflación subyacente) empalmando el histórico oficial
    con la base vigente. Donde ambas series tienen dato para la misma fecha, gana la
    de la base vigente (se agrega después, y append_historico ya se queda con la
    última fila por fecha+serie).
    """
    nombres_temp = [f"_ipc_sae_{i}" for i in range(len(SERIES_IPC_SAE_EMPALME))]
    tabla = cliente.cuadro(series=SERIES_IPC_SAE_EMPALME, nombres=nombres_temp, desde=desde, hasta=hasta)

    filas = []
    for fecha, fila in tabla.iterrows():
        for nombre_temp in nombres_temp:
            valor = fila.get(nombre_temp)
            if valor is None or valor != valor:  # descarta NaN
                continue
            filas.append(
                {"fecha": fecha.date().isoformat(), "serie": "ipc_sae_variacion_mensual", "valor": float(valor)}
            )
    return filas


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

    filas.extend(obtener_ipc_sae_empalmado(cliente, desde=desde, hasta=hasta))
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
