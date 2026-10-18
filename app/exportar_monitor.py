"""Exporta los datos del dashboard como archivos JSON para el «Monitor» (docs/monitor/).

El Monitor es una página estática que NO calcula nada: solo dibuja lo que encuentra acá.
Por eso todo el cálculo (variaciones interanuales, contribuciones, calendario, comentarios)
vive en Python, igual que en el dashboard de Streamlit, y la página solo muestra.

Salidas, en docs/monitor/data/:
  - meta.json              fecha de generación (la página lo consulta para saber si hay datos nuevos)
  - indice.json            resumen de TODAS las series: último valor, variación, tono (mejor/peor) y
                           una mini-serie para la tarjeta; más la definición de las pestañas/tarjetas
  - calendario.json        publicaciones recientes y próximas (ver calendario.py)
  - comentarios.json       comentarios automáticos por plantillas (ver comentarios.py)
  - series/<id>.json       serie completa, para las páginas de detalle

Se corre después de generar_reporte_html.py (ver los workflows de GitHub Actions).
"""

import json
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from calendario import calendario_del_mes, hoy_chile
from comentarios import COMENTARIOS
from config import DEFINICIONES, HISTORICO_PATH, NOMBRES_SERIES, REVISIONES_PATH
from series_utils import (
    calcular_interanual_mensual,
    calcular_ipc_componentes_interanual,
    calcular_masa_salarial_real,
    calcular_total_exportaciones,
    calcular_variacion_mensual_serie,
)

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data"

MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

# Pestañas del Monitor, en orden. "serie" = indicador que encabeza la tarjeta de la portada;
# "secundarias" = indicadores que aparecen como filas pequeñas bajo el gráfico.
TEMAS = [
    {"id": "actividad", "nombre": "Actividad", "icono": "trending-up", "serie": "imacec_interanual",
     "vistas": {"ytd": "imacec_acumulado_anio", "12m": "imacec_anio_movil"},
     "secundarias": ["imacec_sa_mensual", "imacec_minero_interanual", "imacec_no_minero_interanual"]},
    {"id": "precios", "nombre": "Precios", "icono": "tag", "serie": "ipc_mensual",
     "vistas": {"ytd": "ipc_acumulado_anio", "12m": "ipc_interanual"},
     "secundarias": ["ipc_interanual", "ipc_subyacente_interanual", "ipp_interanual"]},
    {"id": "dolar", "nombre": "Dólar y mercado", "icono": "dollar", "serie": "tipo_cambio",
     "vistas": {"ytd": "tipo_cambio_var_anio", "12m": "tipo_cambio_var_12m"},
     "secundarias": ["ipsa", "sp500"]},
    {"id": "tasas", "nombre": "Tasas", "icono": "percent", "serie": "tpm",
     "vistas": {"ytd": "tpm_cambio_anio", "12m": "tpm_cambio_12m"},
     "secundarias": ["eof_inflacion_12m"]},
    {"id": "empleo", "nombre": "Empleo", "icono": "briefcase", "serie": "desempleo",
     "vistas": {"ytd": "desempleo_cambio_anio", "12m": "desempleo_cambio_12m"},
     "secundarias": ["remuneraciones_real_interanual", "masa_salarial_real_interanual"]},
    {"id": "comercio", "nombre": "Comercio exterior", "icono": "globe", "serie": "exportaciones_total_interanual",
     "vistas": {"ytd": "exportaciones_acumulado_anio", "12m": "exportaciones_anio_movil"},
     "secundarias": ["exportaciones_mineria_interanual", "exportaciones_industrial_interanual",
                     "exportaciones_agropecuario_interanual"]},
]


def _raw(h: pd.DataFrame, serie: str) -> pd.DataFrame:
    return h[h["serie"] == serie][["fecha", "valor"]].sort_values("fecha").dropna().reset_index(drop=True)


def _mercado(h: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Serie de mercado sin los días sin rueda: el pipeline intradía deja filas de fin de semana/feriado
    que repiten el último cierre, y comparar contra ellas daría una variación de 0,0% engañosa."""
    df = _raw(h, serie)
    df = df[df["fecha"].dt.weekday < 5]
    return df[df["valor"].diff().fillna(1.0) != 0].reset_index(drop=True)


def _interanual_filas(df: pd.DataFrame) -> pd.DataFrame:
    """% de cambio contra 12 observaciones antes, para un DataFrame mensual fecha/valor."""
    out = df.copy()
    out["valor"] = out["valor"].pct_change(12) * 100
    return out.dropna().reset_index(drop=True)


def _acumulado_anio_variaciones(df: pd.DataFrame) -> pd.DataFrame:
    """Inflación acumulada en el año, componiendo las variaciones mensuales publicadas (con 1 decimal:
    puede diferir unas décimas del acumulado oficial calculado con el índice)."""
    out = df.copy()
    out["valor"] = out.groupby(out["fecha"].dt.year)["valor"].transform(lambda x: ((1 + x / 100).cumprod() - 1) * 100)
    return out


def _acumulado_anio_nivel(df: pd.DataFrame) -> pd.DataFrame:
    """Flujo mensual acumulado en lo que va del año vs. el mismo período del año anterior (%)."""
    out = df.copy()
    out["anio"], out["mes"] = out["fecha"].dt.year, out["fecha"].dt.month
    out["acum"] = out.groupby("anio")["valor"].cumsum()
    previo = out[["anio", "mes", "acum"]].rename(columns={"acum": "acum_previo"})
    previo["anio"] += 1
    out = out.merge(previo, on=["anio", "mes"], how="left")
    out["valor"] = (out["acum"] / out["acum_previo"] - 1) * 100
    return out[["fecha", "valor"]].dropna().reset_index(drop=True)


def _anio_movil_variacion(df: pd.DataFrame) -> pd.DataFrame:
    """Suma de los últimos 12 meses vs. la suma de los 12 meses anteriores (%)."""
    suma = df.set_index("fecha")["valor"].rolling(12).sum()
    out = ((suma / suma.shift(12) - 1) * 100).dropna().reset_index()
    return out.rename(columns={out.columns[1]: "valor"})


def _cambio_desde_cierre_anio(df: pd.DataFrame, relativo: bool) -> pd.DataFrame:
    """Cambio desde el último dato del año anterior (en %, o en puntos si `relativo` es False)."""
    out = df.copy()
    anio = out["fecha"].dt.year
    base = anio.map(out.groupby(anio)["valor"].last().shift(1))
    out["valor"] = (out["valor"] / base - 1) * 100 if relativo else out["valor"] - base
    return out[["fecha", "valor"]].dropna().reset_index(drop=True)


def _cambio_12m(df: pd.DataFrame, relativo: bool) -> pd.DataFrame:
    """Cambio contra el dato de hace un año (el último disponible a esa fecha), en % o en puntos."""
    izq = df.assign(ref=df["fecha"] - pd.DateOffset(years=1)).sort_values("ref")
    der = df.rename(columns={"fecha": "fecha_ref", "valor": "valor_ref"}).sort_values("fecha_ref")
    m = pd.merge_asof(izq, der, left_on="ref", right_on="fecha_ref", direction="backward").dropna()
    m["valor"] = (m["valor"] / m["valor_ref"] - 1) * 100 if relativo else m["valor"] - m["valor_ref"]
    return m[["fecha", "valor"]].sort_values("fecha").reset_index(drop=True)


def _col(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    return df[["fecha", columna]].rename(columns={columna: "valor"}).dropna().reset_index(drop=True)


# Registro de series del Monitor. `datos(h)` devuelve un DataFrame fecha/valor.
#   frecuencia: M mensual, T trimestral, D diaria/irregular (se muestra la fecha exacta)
#   delta: "pp" = diferencia en puntos (series que ya están en %), "rel" = % de cambio (niveles)
#   polaridad: si que suba es bueno / malo para la economía, o neutral (sin juicio de valor)
#   firmado: mostrar el signo + en el valor (variaciones sí, niveles no)
SERIES = [
    # --- Actividad
    dict(id="imacec_interanual", nombre="IMACEC interanual", tema="actividad", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación del IMACEC respecto al mismo mes del año anterior, la forma habitual de reportarlo. "
                    "Es un proxy mensual del PIB, no el PIB trimestral oficial.",
         datos=lambda h: calcular_interanual_mensual(h, "imacec")),
    dict(id="imacec_sa_mensual", nombre="IMACEC desest. mensual", tema="actividad", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación del IMACEC desestacionalizado respecto al mes anterior: así titula el dato el Banco Central.",
         datos=lambda h: calcular_variacion_mensual_serie(h, "imacec_sa")),
    dict(id="imacec_minero_interanual", nombre="IMACEC minero interanual", tema="actividad", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual del IMACEC minero.",
         datos=lambda h: calcular_interanual_mensual(h, "imacec_minero")),
    dict(id="imacec_no_minero_interanual", nombre="IMACEC no minero interanual", tema="actividad", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual del IMACEC sin minería: la actividad del resto de la economía.",
         datos=lambda h: calcular_interanual_mensual(h, "imacec_no_minero")),
    dict(id="eee_pib_actual", nombre="Expectativa de crecimiento del año", tema="actividad", unidad="%", frecuencia="D",
         delta="pp", polaridad="sube_bueno", firmado=False, fuente="Banco Central (EEE)",
         definicion=DEFINICIONES.get("eee_pib_actual", ""), datos=lambda h: _raw(h, "eee_pib_actual")),
    # --- Precios
    dict(id="ipc_mensual", nombre="IPC var. mensual", tema="precios", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_malo", firmado=True, fuente="INE",
         definicion="Variación mensual del IPC general (total nacional): la inflación oficial del mes.",
         datos=lambda h: _raw(h, "ipc_variacion_mensual")),
    dict(id="ipc_interanual", meta=3, nombre="IPC interanual", tema="precios", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_malo", firmado=True, fuente="INE / Banco Central",
         definicion="Variación del IPC respecto al mismo mes del año anterior (inflación a 12 meses).",
         datos=lambda h: _raw(h, "ipc_v12")),
    dict(id="ipc_subyacente_interanual", meta=3, nombre="IPC subyacente interanual", tema="precios", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE / Banco Central",
         definicion="IPC sin alimentos ni energía (SAE), variación interanual: la tendencia de fondo de los precios.",
         datos=lambda h: calcular_ipc_componentes_interanual(h)["IPC subyacente (SAE: sin alimentos ni energía)"]),
    dict(id="ipc_sin_volatiles_interanual", meta=3, nombre="IPC sin volátiles interanual", tema="precios", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_malo", firmado=True, fuente="INE / Banco Central",
         definicion="IPC sin los componentes de precio más cambiante, variación interanual.",
         datos=lambda h: _raw(h, "ipc_sin_volatiles_v12")),
    dict(id="ipp_interanual", nombre="IPP interanual", tema="precios", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_malo", firmado=True, fuente="INE",
         definicion="Índice de precios al productor (general), variación interanual.",
         datos=lambda h: calcular_interanual_mensual(h, "ipp_general")),
    # --- Dólar y mercado
    dict(id="tipo_cambio", nombre="Dólar observado", tema="dolar", unidad="CLP", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=2, fuente="Yahoo Finance",
         definicion=DEFINICIONES.get("tipo_cambio", "Pesos chilenos por dólar."), datos=lambda h: _mercado(h, "tipo_cambio")),
    dict(id="ipsa", nombre="IPSA (vía ETF)", tema="dolar", unidad="CLP", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=2, fuente="Yahoo Finance",
         definicion="Proxy continuo del IPSA: el ETF que lo replica (el índice directo no tiene historia completa).",
         datos=lambda h: _mercado(h, "ipsa_etf")),
    dict(id="sp500", nombre="S&P 500", tema="dolar", unidad="puntos", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=0, fuente="Yahoo Finance",
         definicion="Índice bursátil de las 500 mayores empresas de EE.UU.", datos=lambda h: _mercado(h, "sp500")),
    # --- Tasas
    dict(id="tpm", nombre="Tasa de política monetaria", tema="tasas", unidad="%", frecuencia="D", delta="pp",
         polaridad="neutral", firmado=False, decimales=2, fuente="Banco Central",
         definicion="Tasa de referencia que fija el Consejo del Banco Central en cada reunión de política monetaria.",
         datos=lambda h: _raw(h, "tpm")),
    dict(id="eof_inflacion_12m", meta=3, nombre="Expectativa de inflación a 12 meses", tema="tasas", unidad="%", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=False, fuente="Banco Central (EOF)",
         definicion=DEFINICIONES.get("eof_inflacion_12m", ""), datos=lambda h: _raw(h, "eof_inflacion_12m")),
    # --- Empleo
    dict(id="desempleo", nombre="Tasa de desempleo", tema="empleo", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_malo", firmado=False, fuente="INE",
         definicion="Porcentaje de la fuerza de trabajo que está desocupada (trimestre móvil, ENE).",
         datos=lambda h: _raw(h, "desempleo")),
    dict(id="remuneraciones_real_interanual", nombre="Remuneración real interanual", tema="empleo", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="INE",
         definicion="Variación interanual del índice real de remuneraciones por hora (descontada la inflación).",
         datos=lambda h: calcular_interanual_mensual(h, "remuneraciones_real")),
    dict(id="masa_salarial_real_interanual", nombre="Masa salarial real (aprox.) interanual", tema="empleo", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Cálculo propio",
         definicion="Aproximación propia, no oficial: índice real de remuneraciones x ocupados asalariados. No captura "
                    "cambios en las horas trabajadas.",
         datos=lambda h: _col(calcular_masa_salarial_real(h), "interanual")),
    # --- Vistas "en lo que va del año" y "últimos 12 meses" de las tarjetas de la portada
    dict(id="ipc_acumulado_anio", nombre="IPC acumulado en el año (aprox.)", tema="precios", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE (cálculo propio)",
         definicion="Inflación acumulada desde enero, componiendo las variaciones mensuales publicadas (con un decimal). "
                    "Puede diferir unas décimas del acumulado oficial, que se calcula con el índice sin redondear.",
         datos=lambda h: _acumulado_anio_variaciones(_raw(h, "ipc_variacion_mensual"))),
    dict(id="imacec_acumulado_anio", nombre="IMACEC acumulado en el año", tema="actividad", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Crecimiento del IMACEC en lo que va del año: suma de los meses transcurridos vs. los mismos meses "
                    "del año anterior.",
         datos=lambda h: _acumulado_anio_nivel(_raw(h, "imacec"))),
    dict(id="imacec_anio_movil", nombre="IMACEC año móvil (12 meses)", tema="actividad", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Crecimiento de los últimos 12 meses del IMACEC vs. los 12 meses anteriores: suaviza el ruido de cada mes.",
         datos=lambda h: _anio_movil_variacion(_raw(h, "imacec"))),
    dict(id="tipo_cambio_var_anio", nombre="Dólar: variación en el año", tema="dolar", unidad="%", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=True, fuente="Yahoo Finance (cálculo propio)",
         definicion="Variación del dólar desde el último cierre del año anterior.",
         datos=lambda h: _cambio_desde_cierre_anio(_mercado(h, "tipo_cambio"), relativo=True)),
    dict(id="tipo_cambio_var_12m", nombre="Dólar: variación en 12 meses", tema="dolar", unidad="%", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=True, fuente="Yahoo Finance (cálculo propio)",
         definicion="Variación del dólar contra el valor de hace un año.",
         datos=lambda h: _cambio_12m(_mercado(h, "tipo_cambio"), relativo=True)),
    dict(id="tpm_cambio_anio", nombre="TPM: cambio en el año", tema="tasas", unidad="pp", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=True, decimales=2, fuente="Banco Central (cálculo propio)",
         definicion="Cambio de la TPM, en puntos porcentuales, desde el último dato del año anterior.",
         datos=lambda h: _cambio_desde_cierre_anio(_raw(h, "tpm"), relativo=False)),
    dict(id="tpm_cambio_12m", nombre="TPM: cambio en 12 meses", tema="tasas", unidad="pp", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=True, decimales=2, fuente="Banco Central (cálculo propio)",
         definicion="Cambio de la TPM, en puntos porcentuales, respecto de hace un año.",
         datos=lambda h: _cambio_12m(_raw(h, "tpm"), relativo=False)),
    dict(id="desempleo_cambio_anio", nombre="Desempleo: cambio en el año", tema="empleo", unidad="pp", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE (cálculo propio)",
         definicion="Cambio de la tasa de desempleo, en puntos porcentuales, desde el último dato del año anterior.",
         datos=lambda h: _cambio_desde_cierre_anio(_raw(h, "desempleo"), relativo=False)),
    dict(id="desempleo_cambio_12m", nombre="Desempleo: cambio en 12 meses", tema="empleo", unidad="pp", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE (cálculo propio)",
         definicion="Cambio de la tasa de desempleo, en puntos porcentuales, respecto del mismo trimestre móvil del año anterior.",
         datos=lambda h: _cambio_12m(_raw(h, "desempleo"), relativo=False)),
    dict(id="exportaciones_acumulado_anio", nombre="Exportaciones acumuladas en el año", tema="comercio", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Exportaciones de bienes en lo que va del año vs. los mismos meses del año anterior (FOB).",
         datos=lambda h: _acumulado_anio_nivel(calcular_total_exportaciones(h))),
    dict(id="exportaciones_anio_movil", nombre="Exportaciones año móvil (12 meses)", tema="comercio", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Exportaciones de bienes de los últimos 12 meses vs. los 12 meses anteriores (FOB).",
         datos=lambda h: _anio_movil_variacion(calcular_total_exportaciones(h))),
    # --- Comercio exterior
    dict(id="exportaciones_total_interanual", nombre="Exportaciones de bienes interanual", tema="comercio", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual de las exportaciones de bienes (minería + agro-silvícola-pesquero + industrial), "
                    "FOB. No incluye servicios.",
         datos=lambda h: _interanual_filas(calcular_total_exportaciones(h))),
    dict(id="exportaciones_mineria_interanual", nombre="Exportaciones mineras interanual", tema="comercio", unidad="%",
         frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual de las exportaciones mineras (FOB).",
         datos=lambda h: calcular_interanual_mensual(h, "exportaciones_mineria")),
    dict(id="exportaciones_industrial_interanual", nombre="Exportaciones industriales interanual", tema="comercio",
         unidad="%", frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual de las exportaciones industriales (FOB).",
         datos=lambda h: calcular_interanual_mensual(h, "exportaciones_industrial")),
    dict(id="exportaciones_agropecuario_interanual", nombre="Exportaciones agropecuarias interanual", tema="comercio",
         unidad="%", frecuencia="M", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
         definicion="Variación interanual de las exportaciones agropecuario-silvícola-pesqueras (FOB).",
         datos=lambda h: calcular_interanual_mensual(h, "exportaciones_agropecuario")),
]

# Antigüedad máxima esperada del último dato (días desde su fecha) antes de considerar la serie "demorada".
# Se calcula como el peor caso entre dos publicaciones: la fecha de un dato es el día 1 de su mes, y el siguiente
# se publica cerca de 2 meses después (IPC ~día 8, IPP ~día 24, IMACEC 1er día hábil, ENE ~día 29, etc.) + margen.
MAX_DIAS_POR_SERIE = {
    "imacec": 100, "ipc": 80, "ipp": 92, "eee": 45, "eof": 45, "desempleo": 97, "remuneraciones": 97,
    "masa_salarial": 97, "exportaciones": 80, "tipo_cambio": 7, "ipsa": 7, "sp500": 7, "tpm": 7,
}


def _max_dias(spec_id: str) -> int:
    for prefijo, dias in MAX_DIAS_POR_SERIE.items():
        if spec_id.startswith(prefijo):
            return dias
    return 100


# Cuántos puntos llevan las mini-series de las tarjetas (≈3 años mensuales, ≈6 meses diarios)
PUNTOS_MINI = {"M": 36, "T": 16, "D": 130}


def _redondear(v: float) -> float:
    return round(float(v), 4)


def _filas(df: pd.DataFrame) -> list[list]:
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["valor"])
    return [[f.strftime("%Y-%m-%d"), _redondear(v)] for f, v in zip(df["fecha"], df["valor"])]


def _etiqueta_periodo(fecha: pd.Timestamp, frecuencia: str) -> str:
    if frecuencia == "M":
        return f"{MESES_CORTOS[fecha.month - 1]} {fecha.year}"
    if frecuencia == "T":
        return f"T{(fecha.month - 1) // 3 + 1} {fecha.year}"
    return fecha.strftime("%d-%m-%Y")


def _tono(delta: float | None, polaridad: str, umbral: float) -> str | None:
    if delta is None or polaridad == "neutral":
        return None
    if abs(delta) < umbral:
        return "igual"
    return "mejor" if (delta > 0) == (polaridad == "sube_bueno") else "peor"


def _tipo_grafico(spec: dict) -> str:
    """Las variaciones de un mes contra el anterior se ven mejor como barras (el signo salta a la
    vista); los niveles, las tasas, las variaciones interanuales y las series diarias, como línea."""
    return "barras" if spec["id"].endswith("_mensual") else "linea"


def _resumen(spec: dict, df: pd.DataFrame) -> dict:
    frecuencia = spec["frecuencia"]
    ultimo, previo = df.iloc[-1], (df.iloc[-2] if len(df) > 1 else None)
    delta = None
    if previo is not None:
        if spec["delta"] == "pp":
            delta = float(ultimo["valor"] - previo["valor"])
        elif previo["valor"] != 0:
            delta = float((ultimo["valor"] / previo["valor"] - 1) * 100)
    return {
        "id": spec["id"],
        "nombre": spec["nombre"],
        "tema": spec["tema"],
        "unidad": spec["unidad"],
        "frecuencia": frecuencia,
        "delta_tipo": spec["delta"],
        "firmado": spec["firmado"],
        "decimales": spec.get("decimales", 1),
        "polaridad": spec["polaridad"],
        "fuente": spec["fuente"],
        "tipo": _tipo_grafico(spec),
        "max_dias": _max_dias(spec["id"]),
        "definicion": spec["definicion"],
        "ultimo": {"fecha": ultimo["fecha"].strftime("%Y-%m-%d"), "valor": _redondear(ultimo["valor"]),
                   "etiqueta": _etiqueta_periodo(ultimo["fecha"], frecuencia)},
        "previo": None if previo is None else {
            "fecha": previo["fecha"].strftime("%Y-%m-%d"), "valor": _redondear(previo["valor"]),
            "etiqueta": _etiqueta_periodo(previo["fecha"], frecuencia)},
        "delta": None if delta is None else _redondear(delta),
        "tono": _tono(delta, spec["polaridad"], 0.05),
        "mini": _filas(df.tail(PUNTOS_MINI.get(frecuencia, 36))),
    }


# Series del Monitor -> series de historico.csv cuyas revisiones explican cambios en ellas (ver data/revisiones.csv).
# unidad: cómo mostrar el valor revisado.
REVISIONES_DE = {
    "imacec_interanual": [("imacec", "")], "imacec_minero_interanual": [("imacec_minero", "")],
    "imacec_no_minero_interanual": [("imacec_no_minero", "")], "imacec_sa_mensual": [("imacec_sa", "")],
    "imacec_acumulado_anio": [("imacec", "")], "imacec_anio_movil": [("imacec", "")],
    "ipc_mensual": [("ipc_variacion_mensual", "%")], "ipc_acumulado_anio": [("ipc_variacion_mensual", "%")],
    "ipc_interanual": [("ipc_v12", "%")], "ipc_sin_volatiles_interanual": [("ipc_sin_volatiles_v12", "%")],
    "ipp_interanual": [("ipp_general", "")], "desempleo": [("desempleo", "%")],
    "remuneraciones_real_interanual": [("remuneraciones_real", "")],
    "exportaciones_total_interanual": [("exportaciones_mineria", ""), ("exportaciones_agropecuario", ""), ("exportaciones_industrial", "")],
    "exportaciones_mineria_interanual": [("exportaciones_mineria", "")],
    "exportaciones_industrial_interanual": [("exportaciones_industrial", "")],
    "exportaciones_agropecuario_interanual": [("exportaciones_agropecuario", "")],
}
MAX_REVISIONES = 30


def _revisiones_de(spec_id: str, revisiones: pd.DataFrame | None) -> list[dict]:
    """Últimos valores revisados que afectan a esta serie: el valor anterior no se pierde (ver common.py)."""
    if revisiones is None or revisiones.empty or spec_id not in REVISIONES_DE:
        return []
    filas = []
    for raw, unidad in REVISIONES_DE[spec_id]:
        sub = revisiones[revisiones["serie"] == raw]
        for r in sub.itertuples(index=False):
            filas.append({"serie": NOMBRES_SERIES.get(raw, raw), "unidad": unidad, "fecha": str(r.fecha)[:10],
                          "anterior": _redondear(r.valor_anterior), "nuevo": _redondear(r.valor_nuevo),
                          "detectado": str(r.detectado_el)[:10]})
    filas.sort(key=lambda f: (f["detectado"], f["fecha"]), reverse=True)
    return filas[:MAX_REVISIONES]


def _escribir(ruta: Path, contenido: dict | list) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


# Qué tarjeta muestra el valor de cada publicación del calendario (ver calendario.NOMBRES_PUBLICACION)
TARJETA_DE_EVENTO = {
    "ipc_variacion_mensual": "ipc_mensual",
    "desempleo": "desempleo",
    "imacec": "imacec_interanual",
    "tpm": "tpm",
    "ipp_general": "ipp_interanual",
}


def _mes_desplazado(anio: int, mes: int, delta: int) -> tuple[int, int]:
    indice = anio * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def construir_calendario(h: pd.DataFrame, hoy: date) -> dict:
    """Últimas publicaciones y próximas, mezclando mes anterior, actual y siguiente."""
    eventos = []
    for desplazamiento in (-1, 0, 1):
        anio, mes = _mes_desplazado(hoy.year, hoy.month, desplazamiento)
        eventos.extend(calendario_del_mes(anio, mes, h, hoy))
    eventos.sort(key=lambda e: e["fecha"])

    def estado(e: dict) -> str:
        if e["cargado"]:
            return "cargado"
        if e["fecha"] > hoy:
            return "pendiente"
        return "hoy" if e["fecha"] == hoy else "sin_cargar"

    salida = [
        {
            "fecha": e["fecha"].isoformat(),
            "indicador": e["indicador"],
            "aproximado": e["aproximado"],
            "estado": estado(e),
            "tarjeta": TARJETA_DE_EVENTO.get(e["serie_dato"]),
        }
        for e in eventos
    ]
    pasados = [e for e in salida if e["fecha"] <= hoy.isoformat()][-4:]
    futuros = [e for e in salida if e["fecha"] > hoy.isoformat()][:8]
    return {"hoy": hoy.isoformat(), "eventos": pasados + futuros}


def generar() -> None:
    h = pd.read_csv(HISTORICO_PATH, parse_dates=["fecha"])
    hoy = hoy_chile()

    revisiones = pd.read_csv(REVISIONES_PATH) if REVISIONES_PATH.exists() else None
    resumenes = []
    for spec in SERIES:
        df = spec["datos"](h)
        if df is None or df.empty:
            print(f"  (sin datos para {spec['id']}, se omite)")
            continue
        df = df[["fecha", "valor"]].replace([np.inf, -np.inf], np.nan).dropna().reset_index(drop=True)
        resumenes.append(_resumen(spec, df))
        _escribir(
            SALIDA / "series" / f"{spec['id']}.json",
            {
                "id": spec["id"], "nombre": spec["nombre"], "tema": spec["tema"], "unidad": spec["unidad"],
                "frecuencia": spec["frecuencia"], "fuente": spec["fuente"], "definicion": spec["definicion"],
                "decimales": spec.get("decimales", 1), "firmado": spec["firmado"], "tipo": _tipo_grafico(spec),
                "meta": spec.get("meta"), "revisiones": _revisiones_de(spec["id"], revisiones),
                "datos": _filas(df),
            },
        )

    disponibles = {r["id"] for r in resumenes}
    temas = []
    for tema in TEMAS:
        if tema["serie"] not in disponibles:
            continue
        temas.append({**tema, "secundarias": [s for s in tema["secundarias"] if s in disponibles]})
    _escribir(SALIDA / "indice.json", {"temas": temas, "series": resumenes})

    _escribir(SALIDA / "calendario.json", construir_calendario(h, hoy))

    comentarios = []
    for _clave, (titulo, funcion, _serie) in COMENTARIOS.items():
        texto = funcion(h)
        if texto:
            comentarios.append({"titulo": titulo, "texto": texto})
    _escribir(SALIDA / "comentarios.json", comentarios)

    _escribir(SALIDA / "meta.json", {"generado": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    print(f"Monitor: {len(resumenes)} series exportadas a {SALIDA}")


if __name__ == "__main__":
    generar()
