"""Trae series macro del Banco Central (TPM, IPC, desempleo, IMACEC, tipo de cambio)
y las agrega a data/historico.csv.

IMPORTANTE: los códigos de series abajo deben confirmarse corriendo
`python buscar_series.py "<palabra clave>"` una vez que tengas credenciales del BCCh
(ver README.md). Los códigos exactos varían según la metodología/base del INE vigente,
así que no hay que asumirlos de memoria.
"""

import argparse
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
    # Exportaciones de bienes por sector (FOB, millones de USD, mensual, NO desestacionalizado
    # — por eso los indicadores calculados usan variación interanual, no mes contra mes, para
    # no confundir estacionalidad de la fruta con una caída/alza real). Fuente: Balanza de Pagos.
    "exportaciones_mineria": "F068.B1.FLU.A.0.C.N.Z.Z.Z.Z.6.0.M",
    "exportaciones_agropecuario": "F068.B1.FLU.B.0.C.N.Z.Z.Z.Z.6.0.M",
    "exportaciones_industrial": "F068.B1.FLU.C.0.C.N.Z.Z.Z.Z.6.0.M",
    # IMACEC por sector, base 2018, mensual. "_sa" = desestacionalizado (el resto es
    # serie original). Las "_c_*" son la CONTRIBUCIÓN de cada sector a la variación
    # interanual del IMACEC, en puntos porcentuales: publicadas por el BCCh, y las 6
    # suman exactamente el total (verificado 2014-2026, diferencia máxima 0,0 pp).
    "imacec_sa": "F032.IMC.IND.Z.Z.EP18.Z.Z.1.M",
    "imacec_minero": "F032.IMC.IND.Z.Z.EP18.03.Z.0.M",
    "imacec_minero_sa": "F032.IMC.IND.Z.Z.EP18.03.Z.1.M",
    "imacec_no_minero": "F032.IMC.IND.Z.Z.EP18.N03.Z.0.M",
    "imacec_no_minero_sa": "F032.IMC.IND.Z.Z.EP18.N03.Z.1.M",
    "imacec_c_minero": "F032.IMC.V12.Z.Z.2018.03.Z.0.M",
    "imacec_c_industria": "F032.IMC.V12.Z.Z.2018.04.Z.0.M",
    "imacec_c_resto_bienes": "F032.IMC.V12.Z.Z.2018.RB.Z.0.M",
    "imacec_c_comercio": "F032.IMC.V12.Z.Z.2018.COM.Z.0.M",
    "imacec_c_servicios": "F032.IMC.V12.Z.Z.2018.SERV.Z.0.M",
    "imacec_c_impuestos": "F032.IMC.V12.Z.Z.2018.IMP.Z.0.M",
    # Remuneraciones (INE, índice IR, base 2023=100, serie empalmada) y ocupados
    # asalariados (ENE): insumos de la "masa salarial real" aproximada (no existe
    # una serie oficial con ese nombre, ver series_utils.calcular_masa_salarial_real).
    "remuneraciones_real": "G049.RMM.IND.INE23.R.M",
    "remuneraciones_nominal": "G049.RMM.IND.INE23.NE.M",
    "ocupados_asalariados": "F049.OCU.PMT.INE9.87.M",
    # IPC: variación anual OFICIAL (en vez de componerla desde variaciones mensuales
    # redondeadas a 1 decimal, que se desvía hasta ~0,04 pp), e índice del IPC SAE
    # (subyacente) para calcular su variación anual sin ese error de redondeo.
    "ipc_v12": "G073.IPC.V12.2023.M",
    "ipc_sae_indice": "F074.IPCSAE.IND.Z.EP23.Z.M",
    # IPC SAE (subyacente), variación mensual: serie EMPALMADA OFICIAL del BCCh (cifras INE).
    # Reemplaza el empalme manual que había acá antes, que estaba mal en 2023 (ej. feb-2023:
    # 0,6 vs 0,2 oficial). Si el INE vuelve a cambiar de base habrá que cambiar EP23 por la
    # nueva serie empalmada (ver buscar_series.py "IPC SAE").
    "ipc_sae_variacion_mensual": "F074.IPCSAE.VAR.Z.EP23.Z.M",
    "ipc_sin_volatiles_v12": "G073.IPCSV.V12.2023.M",
    "ipc_bienes_sin_volatiles_v12": "G073.IPCBSV.V12.2023.M",
    "ipc_servicios_sin_volatiles_v12": "G073.IPCSSV.V12.2023.M",
    "ipc_volatiles_v12": "G073.IPCV.V12.2023.M",
    # Tasas bancarias (colocación/captación) pendientes: los códigos F022.COL.TIP.AN01.NO.Z.D
    # y F022.CAP.TIP.AN01.NO.Z.D dan valores que no calzan con la TPM (ej. 1.76% cuando la
    # TPM estaba en 10.75%), y la API no expone la unidad exacta para confirmarlo. No se
    # agregan hasta verificar qué representan realmente.
}

def obtener_expectativas_pib(cliente, desde: str, hasta: str) -> list[dict]:
    """Expectativa de crecimiento del PIB (Encuesta de Expectativas Económicas,
    EEE) para el año en curso y el próximo, mediana de los encuestados.

    El código de la serie en el BCCh depende del año calendario
    (F089.PIB.V12.2026.M, el año que viene será F089.PIB.V12.2027.M, etc.), así
    que se arma acá dinámicamente según la fecha de hoy, para no tener que
    tocar el código cada enero. Como resultado, "eee_pib_actual"/"eee_pib_proximo"
    son series empalmadas de facto: en 2026 reflejan el código de 2026, en 2027
    reflejarán el código de 2027, y así — el nombre siempre significa "el año
    en curso" y "el año siguiente", no un año fijo.

    No se backfillea hacia atrás (solo acumula desde que se empezó a pedir):
    para eso habría que encadenar el código de cada año histórico por separado,
    como se hizo con el IPC SAE, y no hace falta para el uso que se le da acá.
    """
    anio_actual = date.today().year
    codigos = {
        "eee_pib_actual": f"F089.PIB.V12.{anio_actual}.M",
        "eee_pib_proximo": f"F089.PIB.V12.{anio_actual + 1}.M",
    }
    tabla = cliente.cuadro(series=list(codigos.values()), nombres=list(codigos.keys()), desde=desde, hasta=hasta)

    filas = []
    for fecha, fila in tabla.iterrows():
        for nombre in codigos:
            valor = fila.get(nombre)
            if valor is None or valor != valor:  # descarta NaN
                continue
            filas.append({"fecha": fecha.date().isoformat(), "serie": nombre, "valor": float(valor)})
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

    filas.extend(obtener_expectativas_pib(cliente, desde=desde, hasta=hasta))
    return filas


# El Banco Central REVISA meses anteriores cada vez que publica (típico del IMACEC y el
# PIB). Con una ventana de solo 45 días esas revisiones nunca se recogían y el CSV
# quedaba con cifras viejas (se detectó en octubre 2026: junio figuraba +2,41% cuando
# ya estaba en +2,02%). 24 meses cubre las revisiones habituales; el valor anterior
# queda archivado en revisiones.csv (ver common.append_historico).
VENTANA_DIAS = 730


def main() -> None:
    parser = argparse.ArgumentParser(description="Trae series del Banco Central a data/historico.csv")
    parser.add_argument("--desde", help="fecha YYYY-MM-DD de inicio (por defecto, los últimos 24 meses)")
    args = parser.parse_args()
    desde = args.desde or (date.today() - timedelta(days=VENTANA_DIAS)).isoformat()
    filas = obtener_datos(desde=desde)
    if not filas:
        print("No se obtuvieron datos del BCCh.")
        return
    agregadas = append_historico(filas, registrar_revisiones=True)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")


if __name__ == "__main__":
    main()
