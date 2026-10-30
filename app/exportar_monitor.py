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
from calendario_eeuu import eventos_eeuu
from comentarios import COMENTARIOS
from composicion import construir_composicion
from monitor_graficos import GRAFICOS
from config import DEFINICIONES, HISTORICO_PATH, NOMBRES_SERIES, REVISIONES_PATH, OCDE_PAISES_PATH
from series_utils import (
    calcular_anio_movil,
    calcular_imacec_tendencia,
    calcular_interanual_mensual,
    resumir_revisiones,
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
     "graficos": ["crecimiento_chile_ocde_mundo", "contribuciones_imacec", "imacec_total_minero", "imacec_sa_niveles", "pib_tendencia"],
     "vistas": {"ytd": "imacec_acumulado_anio", "12m": "imacec_anio_movil"},
     "secundarias": ["imacec_sa_mensual", "pib_real_interanual", "imacec_minero_interanual", "imacec_no_minero_interanual"]},
    {"id": "precios", "nombre": "Precios", "icono": "tag", "serie": "ipc_mensual",
     "graficos": ["ipc_subyacente", "ipc_aperturas", "ipc_vs_deflactor", "ipp_sectores_interanual", "ipp_sectores_mensual"],
     "vistas": {"ytd": "ipc_acumulado_anio", "12m": "ipc_interanual"},
     "secundarias": ["ipc_interanual", "ipc_subyacente_interanual", "ipp_mensual", "ipp_interanual"]},
    {"id": "dolar", "nombre": "Dólar y mercado", "icono": "dollar", "serie": "tipo_cambio",
     "graficos": ["cobre_vs_exportaciones"],
     "vistas": {"ytd": "tipo_cambio_var_anio", "12m": "tipo_cambio_var_12m"},
     "secundarias": ["cobre_precio", "ipsa", "sp500", "vix"]},
    {"id": "tasas", "nombre": "Tasas", "icono": "percent", "serie": "tpm",
     "vistas": {"ytd": "tpm_cambio_anio", "12m": "tpm_cambio_12m"},
     "secundarias": ["eof_inflacion_12m"]},
    {"id": "empleo", "nombre": "Empleo", "icono": "briefcase", "serie": "desempleo",
     "graficos": ["masa_salarial_aportes", "remuneraciones_inflacion", "desempleo_movil"],
     "vistas": {"ytd": "desempleo_cambio_anio", "12m": "desempleo_cambio_12m"},
     "secundarias": ["remuneraciones_real_interanual", "masa_salarial_real_interanual"]},
    {"id": "comercio", "nombre": "Comercio exterior", "icono": "globe", "serie": "exportaciones_total_interanual",
     "graficos": ["exportaciones_sectores_anio_movil"],
     "vistas": {"ytd": "exportaciones_acumulado_anio", "12m": "exportaciones_anio_movil"},
     "secundarias": ["importaciones_interanual", "balanza_comercial", "exportaciones_mineria_interanual", "exportaciones_industrial_interanual",
                     "exportaciones_agropecuario_interanual"]},
    {"id": "eeuu", "nombre": "Estados Unidos", "icono": "flag", "serie": "eeuu_desempleo",
     "graficos": ["pib_pc_chile_eeuu", "pib_estados_eeuu"],
     "secundarias": ["eeuu_inflacion", "eeuu_fed_limite_superior", "eeuu_empleo_no_agricola", "eeuu_ipp_demanda_final"]},
    {"id": "desigualdad", "nombre": "Desigualdad", "icono": "scale", "serie": "chile_gini",
     "graficos": ["gini_chile_eeuu", "gini_estados_eeuu"], "secundarias": ["eeuu_gini"]},
]

# Pestañas que no son un tema con tarjetas sino una sección de gráficos/tablas.
SECCIONES = [
    {"id": "comparador", "nombre": "Comparador", "icono": "globe", "tipo": "comparador",
     "intro": "Compara a Chile con el mundo, la OCDE, otras regiones y cualquier país: crecimiento del PIB (total y per cápita), inflación y "
              "desempleo, desde 1990. Por defecto aparece Chile contra la OCDE y el mundo; agrega o saca las comparaciones que quieras y "
              "el enlace de la página guarda tu selección."},
    {"id": "composicion", "nombre": "Composición del PIB", "icono": "scale", "tipo": "composicion",
     "intro": "De qué está hecho el PIB de Chile y cómo ha cambiado. Parte del total y baja paso a paso: por ejemplo PIB → exportaciones → bienes → "
              "minería → cobre. Para cada componente ves su peso (% del PIB o % de lo que lo contiene) y su evolución en el tiempo."},
    {"id": "ocde", "nombre": "Comparación OCDE", "icono": "globe",
     "intro": "Cómo se ubica Chile frente a los 38 países de la OCDE. Todos los indicadores vienen del Banco Mundial para que estén calculados "
              "con la misma metodología entre países, así que pueden diferir un poco de las cifras oficiales de Chile que se muestran en el resto "
              "del Monitor (por ejemplo, el desempleo acá es una estimación armonizada de la OIT, no la tasa del INE)."},
    {"id": "proyecciones", "nombre": "Proyecciones", "icono": "trending-up",
     "series": ["eee_pib_actual", "eee_pib_proximo", "eof_inflacion_12m"],
     "intro": "Proyecciones estadísticas a 6 meses (ARIMA sobre el historial de cada serie, sin otras variables): no son pronósticos oficiales de "
              "nadie. No se proyectan el dólar (casi un camino aleatorio) ni la TPM (la fija un comité). Para crecimiento esperado, la referencia "
              "más confiable es la Encuesta de Expectativas Económicas (EEE) del Banco Central, que incorpora criterio de mercado."},
    {"id": "revisiones", "nombre": "Revisiones", "icono": "tag", "tipo": "revisiones",
     "intro": "Las fuentes oficiales (Banco Central, INE) revisan cifras de meses anteriores cada vez que publican. Los gráficos del Monitor usan "
              "siempre el valor revisado (el vigente hoy), pero el valor anterior no se descarta: queda archivado acá con la fecha en que se detectó."},
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


def _yoy_fecha(df: pd.DataFrame) -> pd.DataFrame:
    """Variación % contra el MISMO mes del año anterior, emparejando por fecha y no por posición: si falta un mes (como octubre de
    2025 en EE.UU., por el cierre del gobierno) contar "12 filas atrás" se desfasa y da cifras erradas (el IPC de septiembre salía
    4,0% en vez de 3,7%)."""
    s = df.set_index("fecha")["valor"]
    previo = s.reindex(s.index - pd.DateOffset(years=1))
    out = pd.DataFrame({"fecha": s.index, "valor": (s.values / previo.values - 1) * 100})
    return out.dropna().reset_index(drop=True)


def _cambio_mensual_abs(df: pd.DataFrame) -> pd.DataFrame:
    """Cambio contra el mes anterior (por fecha) en las unidades de la serie."""
    s = df.set_index("fecha")["valor"]
    previo = s.reindex(s.index - pd.DateOffset(months=1))
    out = pd.DataFrame({"fecha": s.index, "valor": s.values - previo.values})
    return out.dropna().reset_index(drop=True)


def _col(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    return df[["fecha", columna]].rename(columns={columna: "valor"}).dropna().reset_index(drop=True)


def _escala(df: pd.DataFrame, factor: float) -> pd.DataFrame:
    out = df.copy()
    out["valor"] = out["valor"] * factor
    return out


def _variacion_periodos(df: pd.DataFrame, periodos: int) -> pd.DataFrame:
    out = df.copy()
    out["valor"] = out["valor"].pct_change(periodos) * 100
    return out.dropna().reset_index(drop=True)


def _tpm_real(h: pd.DataFrame) -> pd.DataFrame:
    """TPM menos la inflación interanual oficial de cada mes (TPM vigente a fin de ese mes): TPM real ex-post.
    Positivo = política monetaria restrictiva; negativo = expansiva."""
    ipc, tpm = _raw(h, "ipc_v12"), _raw(h, "tpm")
    izq = ipc.assign(fin_mes=ipc["fecha"] + pd.offsets.MonthEnd(0)).sort_values("fin_mes")
    m = pd.merge_asof(izq, tpm.rename(columns={"fecha": "fecha_tpm", "valor": "tpm"}), left_on="fin_mes", right_on="fecha_tpm")
    m["valor"] = m["tpm"] - m["valor"]
    return m[["fecha", "valor"]].dropna().sort_values("fecha").reset_index(drop=True)


def _simple(id, nombre, tema, datos, unidad="", frecuencia="M", delta="rel", polaridad="neutral", firmado=False,
            fuente="Banco Central", definicion="", clave_def=None, **extra):
    return dict(id=id, nombre=nombre, tema=tema, unidad=unidad, frecuencia=frecuencia, delta=delta, polaridad=polaridad,
                firmado=firmado, fuente=fuente, definicion=definicion or DEFINICIONES.get(clave_def or id, ""), datos=datos, **extra)


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
         definicion="Crecimiento del PIB esperado para el año en curso: mediana de la Encuesta de Expectativas Económicas (EEE) del Banco Central, "
                    "es decir el consenso de mercado (bancos, AFPs, consultoras), no un modelo estadístico. Es la referencia más confiable de crecimiento esperado.", datos=lambda h: _raw(h, "eee_pib_actual")),
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
    dict(id="ipp_interanual", nombre="IPP interanual (12 meses)", tema="precios", unidad="%", frecuencia="M", delta="pp",
         polaridad="sube_malo", firmado=True, fuente="INE",
         definicion="Índice de precios al productor (general), variación interanual.",
         datos=lambda h: calcular_interanual_mensual(h, "ipp_general")),
    # --- Dólar y mercado
    dict(id="tipo_cambio", nombre="Dólar observado", tema="dolar", unidad="CLP", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=2, fuente="Banco Central",
         definicion="Dólar observado: promedio de las transacciones interbancarias del día que calcula y publica el Banco Central (solo días "
                    "hábiles, con un día de rezago). Es el que citan los medios; difiere algo de la cotización de mercado intradía.",
         datos=lambda h: _raw(h, "dolar_observado")),
    dict(id="ipsa", nombre="IPSA (vía ETF)", tema="dolar", unidad="CLP", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=2, fuente="Yahoo Finance",
         definicion="Proxy continuo del IPSA: el ETF que lo replica (el índice directo no tiene historia completa).",
         datos=lambda h: _mercado(h, "ipsa_etf")),
    dict(id="sp500", nombre="S&P 500", tema="dolar", unidad="puntos", frecuencia="D", delta="rel",
         polaridad="neutral", firmado=False, decimales=0, fuente="Yahoo Finance",
         definicion="Índice bursátil de las 500 mayores empresas de EE.UU.", datos=lambda h: _mercado(h, "sp500")),
    dict(id="vix", nombre="VIX (volatilidad del S&P 500)", tema="dolar", unidad="puntos", frecuencia="D", delta="abs",
         polaridad="neutral", firmado=False, decimales=1, fuente="Yahoo Finance (CBOE)",
         definicion="Índice de volatilidad del S&P 500: la variación que el mercado espera para el S&P 500 en los próximos 30 días, calculada con "
                    "precios de opciones. Se le llama «índice del miedo»: bajo 15 hay calma, entre 15 y 30 incertidumbre normal y sobre 30 estrés "
                    "(en marzo de 2020 llegó a 83). Sube fuerte cuando las bolsas caen.",
         datos=lambda h: _mercado(h, "vix")),
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
         definicion="Porcentaje de la fuerza de trabajo que está desocupada (trimestre móvil, ENE). Serie original (sin desestacionalizar), la que titula el INE.",
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
    dict(id="ipc_acumulado_anio", nombre="IPC acumulado en el año", tema="precios", unidad="%", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE / Banco Central",
         definicion="Inflación acumulada desde diciembre del año anterior, calculada con el índice general del IPC (sin redondeos intermedios).",
         datos=lambda h: _cambio_desde_cierre_anio(_raw(h, "ipc_indice"), relativo=True)),
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
         delta="pp", polaridad="neutral", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Variación del dólar observado desde el último valor del año anterior.",
         datos=lambda h: _cambio_desde_cierre_anio(_raw(h, "dolar_observado"), relativo=True)),
    dict(id="tipo_cambio_var_12m", nombre="Dólar: variación en 12 meses", tema="dolar", unidad="%", frecuencia="D",
         delta="pp", polaridad="neutral", firmado=True, fuente="Banco Central (cálculo propio)",
         definicion="Variación del dólar observado contra el valor de hace un año.",
         datos=lambda h: _cambio_12m(_raw(h, "dolar_observado"), relativo=True)),
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
         datos=lambda h: _cambio_desde_cierre_anio(_raw(h, "desempleo").round({"valor": 1}), relativo=False)),
    dict(id="desempleo_cambio_12m", nombre="Desempleo: cambio en 12 meses", tema="empleo", unidad="pp", frecuencia="M",
         delta="pp", polaridad="sube_malo", firmado=True, fuente="INE (cálculo propio)",
         definicion="Cambio de la tasa de desempleo, en puntos porcentuales, respecto del mismo trimestre móvil del año anterior.",
         datos=lambda h: _cambio_12m(_raw(h, "desempleo").round({"valor": 1}), relativo=False)),
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

SERIES += [
    # --- Actividad
    _simple("imacec_indice", "IMACEC (índice)", "actividad", lambda h: _raw(h, "imacec"), unidad="índice", polaridad="sube_bueno",
            decimales=1, clave_def="imacec"),
    _simple("pib_chile", "PIB nominal trimestral (desest.)", "actividad", lambda h: _escala(_raw(h, "pib_chile"), 1 / 1000), unidad="$",
            frecuencia="T", polaridad="sube_bueno", decimales=1, prefijo="$", sufijo=" billones",
            definicion="Valor de todos los bienes y servicios producidos en Chile en el trimestre, a precios corrientes (no descuenta la "
                       "inflación), desestacionalizado. En billones de pesos (millones de millones)."),
    _simple("pib_mineria", "PIB minería (real, desest., mensual)", "actividad", lambda h: _escala(_raw(h, "pib_mineria"), 1 / 1000),
            unidad="$", polaridad="sube_bueno", decimales=2, prefijo="$", sufijo=" billones",
            definicion="PIB del sector minero (principalmente cobre) en volumen, desestacionalizado. En billones de pesos de 2018."),
    _simple("pib_mineria_interanual", "PIB minería interanual", "actividad", lambda h: calcular_interanual_mensual(h, "pib_mineria_original"),
            unidad="%", delta="pp", polaridad="sube_bueno", firmado=True,
            definicion="Variación interanual del PIB minero real, calculada sobre la serie original (sin desestacionalizar), como la publica el Banco Central."),
    _simple("pib_no_minero", "PIB no minero (real, desest., trimestral)", "actividad", lambda h: _escala(_raw(h, "pib_no_minero"), 1 / 1000),
            unidad="$", frecuencia="T", polaridad="sube_bueno", decimales=1, prefijo="$", sufijo=" billones",
            definicion="PIB sin minería en volumen, desestacionalizado: cómo le va al resto de la economía. En billones de pesos de 2018."),
    _simple("pib_no_minero_interanual", "PIB no minero interanual", "actividad",
            lambda h: _variacion_periodos(_raw(h, "pib_no_minero_original"), 4), unidad="%", frecuencia="T", delta="pp",
            polaridad="sube_bueno", firmado=True,
            definicion="Variación interanual (4 trimestres) del PIB no minero real, sobre la serie original (sin desestacionalizar)."),
    _simple("eee_pib_proximo", "Expectativa de crecimiento del año siguiente", "actividad", lambda h: _raw(h, "eee_pib_proximo"),
            unidad="%", frecuencia="D", delta="pp", polaridad="sube_bueno", fuente="Banco Central (EEE)"),
    _simple("chile_pib_per_capita_ppa", "PIB per cápita de Chile (PPA)", "actividad", lambda h: _raw(h, "chile_pib_per_capita_ppa"),
            unidad="US$", frecuencia="A", polaridad="sube_bueno", decimales=0, prefijo="US$", fuente="FMI vía Banco Central",
            definicion="PIB por persona en dólares ajustados por paridad de poder de compra (FMI-WEO). Las cifras del año en curso y siguientes son proyecciones del FMI."),
    _simple("chile_poblacion", "Población de Chile", "actividad", lambda h: _escala(_raw(h, "chile_poblacion"), 1e-6), unidad="personas",
            frecuencia="A", decimales=2, sufijo=" millones", fuente="Banco Mundial",
            definicion="Población total de Chile (dato anual del Banco Mundial). Se usa para calcular el crecimiento per cápita del IMACEC."),
    # --- Precios
    _simple("ipc_sae_mensual", "IPC SAE var. mensual", "precios", lambda h: _raw(h, "ipc_sae_variacion_mensual"), unidad="%",
            delta="pp", polaridad="sube_malo", firmado=True, fuente="INE", clave_def="ipc_sae_variacion_mensual"),
    _simple("ipc_bienes_interanual", "IPC bienes sin volátiles interanual", "precios",
            lambda h: _raw(h, "ipc_bienes_sin_volatiles_v12"), unidad="%", delta="pp", polaridad="sube_malo", firmado=True, meta=3,
            fuente="INE / Banco Central", definicion="Inflación interanual de los bienes sin volátiles (más ligada al dólar)."),
    _simple("ipc_servicios_interanual", "IPC servicios sin volátiles interanual", "precios",
            lambda h: _raw(h, "ipc_servicios_sin_volatiles_v12"), unidad="%", delta="pp", polaridad="sube_malo", firmado=True, meta=3,
            fuente="INE / Banco Central", definicion="Inflación interanual de los servicios sin volátiles (más ligada a salarios)."),
    _simple("ipc_volatiles_interanual", "IPC volátiles interanual", "precios", lambda h: _raw(h, "ipc_volatiles_v12"), unidad="%",
            delta="pp", polaridad="sube_malo", firmado=True, fuente="INE / Banco Central",
            definicion="Inflación interanual de los componentes de precio más cambiante (alimentos frescos, combustibles, etc.)."),
    _simple("pib_deflactor", "Deflactor del PIB (índice)", "precios", lambda h: _raw(h, "pib_deflactor"), unidad="índice",
            frecuencia="T", decimales=1),
    _simple("inflacion_deflactor_interanual", "Inflación por deflactor del PIB", "precios",
            lambda h: _variacion_periodos(_raw(h, "pib_deflactor"), 4), unidad="%", frecuencia="T", delta="pp", polaridad="sube_malo",
            firmado=True, definicion="Variación interanual del deflactor del PIB: inflación de todo lo que produce el país, no solo lo que "
                                     "consumen los hogares; suele reaccionar más al precio del cobre."),
    # --- Tasas
    _simple("tpm_real", "TPM real (ex-post)", "tasas", _tpm_real, unidad="pp", delta="pp", firmado=True, decimales=1,
            fuente="Banco Central (cálculo propio)",
            definicion="TPM menos la inflación interanual del mes. Positivo = política monetaria restrictiva; negativo = expansiva."),
    _simple("eof_tpm_proxima_reunion", "Expectativa de TPM próxima reunión", "tasas", lambda h: _raw(h, "eof_tpm_proxima_reunion"),
            unidad="%", frecuencia="D", delta="pp", decimales=2, fuente="Banco Central (EOF)"),
    # --- Dólar y mercado
    _simple("eof_tipo_cambio_7d", "Expectativa de dólar a 7 días", "dolar", lambda h: _raw(h, "eof_tipo_cambio_7d"), unidad="CLP",
            frecuencia="D", decimales=0, fuente="Banco Central (EOF)"),
    _simple("ipsa_indice_real", "IPSA (índice, datos discontinuos)", "dolar", lambda h: _raw(h, "ipsa_indice_real"), unidad="puntos",
            frecuencia="D", decimales=0, fuente="Yahoo Finance", huecos=45, alerta=False),
    # --- Empleo
    _simple("fuerza_trabajo", "Fuerza de trabajo", "empleo", lambda h: _raw(h, "fuerza_trabajo"), unidad="personas", decimales=0,
            sufijo=" mil", fuente="INE"),
    _simple("ocupados", "Ocupados", "empleo", lambda h: _raw(h, "ocupados"), unidad="personas", polaridad="sube_bueno", decimales=0,
            sufijo=" mil", fuente="INE"),
    _simple("desocupados", "Desocupados", "empleo", lambda h: _raw(h, "desocupados"), unidad="personas", polaridad="sube_malo",
            decimales=0, sufijo=" mil", fuente="INE"),
    # --- Comercio exterior
    _simple("exportaciones_total_mensual", "Exportaciones de bienes (mensual)", "comercio", lambda h: calcular_total_exportaciones(h),
            unidad="US$", polaridad="sube_bueno", decimales=0, prefijo="US$", sufijo=" MM",
            definicion="Suma de minería, agropecuario-silvícola-pesquero e industrial, valor FOB mensual, en millones de dólares. No está "
                       "desestacionalizado: compara contra el mismo mes del año anterior, no contra el mes previo."),
    _simple("exportaciones_mineria", "Exportaciones mineras (mensual)", "comercio", lambda h: _raw(h, "exportaciones_mineria"),
            unidad="US$", polaridad="sube_bueno", decimales=0, prefijo="US$", sufijo=" MM"),
    _simple("exportaciones_agropecuario", "Exportaciones agropecuarias (mensual)", "comercio",
            lambda h: _raw(h, "exportaciones_agropecuario"), unidad="US$", polaridad="sube_bueno", decimales=0, prefijo="US$", sufijo=" MM"),
    _simple("exportaciones_industrial", "Exportaciones industriales (mensual)", "comercio", lambda h: _raw(h, "exportaciones_industrial"),
            unidad="US$", polaridad="sube_bueno", decimales=0, prefijo="US$", sufijo=" MM"),
    _simple("exportaciones_total_anio_movil", "Exportaciones de bienes, año móvil", "comercio",
            lambda h: calcular_anio_movil(calcular_total_exportaciones(h)), unidad="US$", polaridad="sube_bueno", decimales=0,
            prefijo="US$", sufijo=" MM",
            definicion="Suma de los últimos 12 meses de exportaciones de bienes, recalculada cada mes: quita la estacionalidad."),
    # --- Estados Unidos
    _simple("eeuu_desempleo", "EE.UU.: tasa de desempleo", "eeuu", lambda h: _raw(h, "eeuu_desempleo"), unidad="%", delta="pp",
            polaridad="sube_malo", fuente="Banco Central (BLS)", definicion="Tasa de desempleo de Estados Unidos."),
    _simple("eeuu_inflacion", "EE.UU.: inflación interanual (IPC)", "eeuu",
            lambda h: (_yoy_fecha(_raw(h, "eeuu_ipc_indice")) if not _raw(h, "eeuu_ipc_indice").empty else _raw(h, "eeuu_inflacion")), unidad="%",
            delta="pp", polaridad="sube_malo", firmado=True, fuente="BLS (vía FRED)",
            definicion="Variación del IPC de Estados Unidos contra el mismo mes del año anterior (índice sin desestacionalizar, el que titula el BLS)."),
    _simple("eeuu_ipp", "EE.UU.: IPP (todos los commodities) interanual", "eeuu", lambda h: _raw(h, "eeuu_ipp"), unidad="%", delta="pp", polaridad="sube_malo",
            firmado=True, fuente="Banco Central (BLS)",
            definicion="Variación en 12 meses del Índice de Precios al Productor de Estados Unidos, serie «todos los commodities» que publica el Banco Central. "
                       "No es el IPP de «demanda final» que citan los medios: este se mueve bastante más porque pesan más la energía y las materias primas."),
    _simple("eeuu_pib_total", "EE.UU.: PIB total (nominal)", "eeuu", lambda h: _escala(_raw(h, "eeuu_pib_total"), 1 / 1000), unidad="US$",
            frecuencia="T", polaridad="sube_bueno", decimales=1, prefijo="US$", sufijo=" billones", fuente="FRED",
            definicion="PIB de Estados Unidos en dólares corrientes, tasa anual desestacionalizada. En billones de dólares (millones de millones)."),
    _simple("eeuu_pib_per_capita", "EE.UU.: PIB per cápita (PPA)", "eeuu", lambda h: _escala(_raw(h, "eeuu_pib_per_capita"), 1000),
            unidad="US$", frecuencia="A", polaridad="sube_bueno", decimales=0, prefijo="US$", fuente="FMI vía Banco Central"),
    # --- Desigualdad
    _simple("chile_gini", "Chile: índice de Gini", "desigualdad", lambda h: _raw(h, "chile_gini"), unidad="índice", frecuencia="A",
            delta="pp", decimales=1, fuente="Banco Mundial"),
    _simple("eeuu_gini", "EE.UU.: índice de Gini", "desigualdad", lambda h: _raw(h, "eeuu_gini"), unidad="índice", frecuencia="A",
            delta="pp", decimales=1, fuente="Banco Mundial"),
]


SERIES += [
    # --- IPP: el INE lo titula con la variación mensual; acá las tres lecturas (mensual, acumulada en el año, interanual)
    _simple("ipp_mensual", "IPP var. mensual", "precios", lambda h: _variacion_periodos(_raw(h, "ipp_general"), 1), unidad="%", delta="pp",
            polaridad="sube_malo", firmado=True, fuente="INE",
            definicion="Variación mensual del IPP general de industrias (minería, industria manufacturera y electricidad, gas y agua): "
                       "es el dato con que el INE titula cada publicación. Se calcula sobre el índice con dos decimales, así que puede "
                       "diferir una décima de la cifra oficial."),
    _simple("ipp_acumulado_anio", "IPP acumulado en el año", "precios",
            lambda h: _cambio_desde_cierre_anio(_raw(h, "ipp_general"), relativo=True), unidad="%", delta="pp", polaridad="sube_malo",
            firmado=True, fuente="INE (cálculo propio)", definicion="Variación del IPP general desde diciembre del año anterior."),
    _simple("ipp_mineria_mensual", "IPP minería var. mensual", "precios", lambda h: _variacion_periodos(_raw(h, "ipp_mineria"), 1), unidad="%",
            delta="pp", polaridad="sube_malo", firmado=True, fuente="INE",
            definicion="Variación mensual del IPP de la minería (muy ligado al precio del cobre)."),
    _simple("ipp_manufactura_mensual", "IPP manufactura var. mensual", "precios", lambda h: _variacion_periodos(_raw(h, "ipp_manufactura"), 1),
            unidad="%", delta="pp", polaridad="sube_malo", firmado=True, fuente="INE",
            definicion="Variación mensual del IPP de la industria manufacturera."),
    _simple("ipp_ega_mensual", "IPP electricidad, gas y agua var. mensual", "precios", lambda h: _variacion_periodos(_raw(h, "ipp_ega"), 1),
            unidad="%", delta="pp", polaridad="sube_malo", firmado=True, fuente="INE",
            definicion="Variación mensual del IPP de electricidad, gas y agua."),
    # --- Remuneraciones: el INE reporta la variación mensual y la de 12 meses, nominal y real
    _simple("remuneraciones_real_mensual", "Remuneración real var. mensual", "empleo",
            lambda h: _variacion_periodos(_raw(h, "remuneraciones_real"), 1), unidad="%", delta="pp", polaridad="sube_bueno", firmado=True,
            fuente="INE", definicion="Variación mensual del índice real de remuneraciones por hora (descontada la inflación)."),
    _simple("remuneraciones_nominal_mensual", "Remuneración nominal var. mensual", "empleo",
            lambda h: _variacion_periodos(_raw(h, "remuneraciones_nominal"), 1), unidad="%", delta="pp", polaridad="sube_bueno", firmado=True,
            fuente="INE", definicion="Variación mensual del índice nominal de remuneraciones por hora."),
    _simple("remuneraciones_nominal_interanual", "Remuneración nominal interanual", "empleo",
            lambda h: calcular_interanual_mensual(h, "remuneraciones_nominal"), unidad="%", delta="pp", polaridad="sube_bueno", firmado=True,
            fuente="INE", definicion="Variación interanual del índice nominal de remuneraciones por hora."),
]


SERIES += [
    # --- PIB: los dos titulares del Banco Central (interanual sobre la serie original; trimestral sobre la desestacionalizada)
    _simple("pib_real_interanual", "PIB real interanual", "actividad", lambda h: _variacion_periodos(_raw(h, "pib_real"), 4), unidad="%",
            frecuencia="T", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
            definicion="Crecimiento del PIB real (a precios constantes) contra el mismo trimestre del año anterior: el dato con que el Banco Central "
                       "titula las cuentas nacionales."),
    _simple("pib_real_trimestral", "PIB real var. trimestral (desest.)", "actividad", lambda h: _variacion_periodos(_raw(h, "pib_real_sa"), 1),
            unidad="%", frecuencia="T", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
            definicion="Variación del PIB real desestacionalizado contra el trimestre anterior."),
    # --- IMACEC por componente, mes contra mes desestacionalizado
    _simple("imacec_minero_sa_mensual", "IMACEC minero desest. mensual", "actividad", lambda h: calcular_variacion_mensual_serie(h, "imacec_minero_sa"),
            unidad="%", delta="pp", polaridad="sube_bueno", firmado=True, fuente="Banco Central",
            definicion="Variación del IMACEC minero desestacionalizado contra el mes anterior."),
    _simple("imacec_no_minero_sa_mensual", "IMACEC no minero desest. mensual", "actividad",
            lambda h: calcular_variacion_mensual_serie(h, "imacec_no_minero_sa"), unidad="%", delta="pp", polaridad="sube_bueno", firmado=True,
            fuente="Banco Central", definicion="Variación del IMACEC no minero desestacionalizado contra el mes anterior."),
    # --- Empleo: variación a 12 meses de los niveles (como los titula el INE)
    _simple("ocupados_interanual", "Ocupados interanual", "empleo", lambda h: calcular_interanual_mensual(h, "ocupados"), unidad="%", delta="pp",
            polaridad="sube_bueno", firmado=True, fuente="INE", definicion="Variación en 12 meses de los ocupados (serie original, trimestre móvil)."),
    _simple("desocupados_interanual", "Desocupados interanual", "empleo", lambda h: calcular_interanual_mensual(h, "desocupados"), unidad="%",
            delta="pp", polaridad="sube_malo", firmado=True, fuente="INE", definicion="Variación en 12 meses de los desocupados (serie original)."),
    _simple("fuerza_trabajo_interanual", "Fuerza de trabajo interanual", "empleo", lambda h: calcular_interanual_mensual(h, "fuerza_trabajo"),
            unidad="%", delta="pp", fuente="INE", firmado=True, definicion="Variación en 12 meses de la fuerza de trabajo (serie original)."),
    # --- Comercio exterior: importaciones y balanza comercial (FOB, millones de US$)
    _simple("importaciones_mensual", "Importaciones de bienes (mensual)", "comercio", lambda h: _raw(h, "importaciones_bienes"), unidad="US$",
            decimales=0, prefijo="US$", sufijo=" MM", fuente="Banco Central",
            definicion="Importaciones de bienes, valor FOB (balanza de pagos) mensual, en millones de dólares. Es menor que la cifra CIF que suelen citar los medios, "
                       "porque no incluye seguros ni fletes; con FOB la balanza comercial cuadra con la oficial. No desestacionalizado."),
    _simple("importaciones_interanual", "Importaciones de bienes interanual", "comercio", lambda h: calcular_interanual_mensual(h, "importaciones_bienes"),
            unidad="%", delta="pp", firmado=True, fuente="Banco Central", definicion="Variación interanual de las importaciones de bienes (FOB)."),
    _simple("balanza_comercial", "Balanza comercial de bienes (mensual)", "comercio",
            lambda h: (_raw(h, "importaciones_bienes").set_index("fecha")["valor"].rsub(calcular_total_exportaciones(h).set_index("fecha")["valor"]).dropna()
                       .rename("valor").reset_index()),
            unidad="US$", polaridad="sube_bueno", decimales=0, prefijo="US$", sufijo=" MM", firmado=True, fuente="Banco Central (cálculo propio)",
            definicion="Exportaciones menos importaciones de bienes (FOB), en millones de dólares. Positivo = superávit comercial."),
    # --- Bolsa: variación en el año y en 12 meses (como el dólar)
    _simple("ipsa_var_anio", "IPSA: variación en el año", "dolar", lambda h: _cambio_desde_cierre_anio(_mercado(h, "ipsa_etf"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Yahoo Finance (cálculo propio)", definicion="Variación del IPSA (vía ETF) desde el último cierre del año anterior."),
    _simple("ipsa_var_12m", "IPSA: variación en 12 meses", "dolar", lambda h: _cambio_12m(_mercado(h, "ipsa_etf"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Yahoo Finance (cálculo propio)", definicion="Variación del IPSA (vía ETF) contra el valor de hace un año."),
    _simple("sp500_var_anio", "S&P 500: variación en el año", "dolar", lambda h: _cambio_desde_cierre_anio(_mercado(h, "sp500"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Yahoo Finance (cálculo propio)", definicion="Variación del S&P 500 desde el último cierre del año anterior."),
    _simple("sp500_var_12m", "S&P 500: variación en 12 meses", "dolar", lambda h: _cambio_12m(_mercado(h, "sp500"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Yahoo Finance (cálculo propio)", definicion="Variación del S&P 500 contra el valor de hace un año."),
]


SERIES += [
    # --- Precio del cobre (refinado, Bolsa de Metales de Londres): la principal exportación de Chile
    _simple("cobre_precio", "Precio del cobre", "dolar", lambda h: _raw(h, "cobre_precio"), unidad="US$/lb", frecuencia="D", delta="rel",
            polaridad="neutral", decimales=2, prefijo="US$", sufijo="/lb", fuente="Banco Central (Bolsa de Metales de Londres)",
            definicion="Precio del cobre refinado en la Bolsa de Metales de Londres, en dólares por libra: la referencia de lo que cobra Chile por su principal "
                       "exportación (el cobre es ~53% de las exportaciones de bienes). Datos diarios de días hábiles, con un día de rezago."),
    _simple("cobre_var_anio", "Cobre: variación en el año", "dolar", lambda h: _cambio_desde_cierre_anio(_raw(h, "cobre_precio"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Banco Central (cálculo propio)", definicion="Variación del precio del cobre desde el último valor del año anterior."),
    _simple("cobre_var_12m", "Cobre: variación en 12 meses", "dolar", lambda h: _cambio_12m(_raw(h, "cobre_precio"), relativo=True), unidad="%",
            frecuencia="D", delta="pp", firmado=True, fuente="Banco Central (cálculo propio)", definicion="Variación del precio del cobre contra el valor de hace un año."),
    _simple("cobre_precio_promedio", "Precio del cobre, promedio mensual (desde 1960)", "dolar", lambda h: _raw(h, "cobre_precio_promedio"), unidad="US$/lb",
            decimales=2, prefijo="US$", sufijo="/lb", fuente="Banco Central (valores referenciales)",
            definicion="Promedio mensual del precio del cobre refinado (US$/libra), con historia desde 1960: sirve para ver los grandes ciclos (el «súper ciclo» de "
                       "2005-2011, la caída de 2015 y el repunte reciente). Valores referenciales, sin deflactar: no descuentan la inflación de EE.UU."),
    _simple("cobre_precio_interanual", "Precio del cobre interanual (promedio mensual)", "dolar", lambda h: calcular_interanual_mensual(h, "cobre_precio_promedio"),
            unidad="%", delta="pp", firmado=True, fuente="Banco Central (cálculo propio)",
            definicion="Variación del precio promedio mensual del cobre contra el mismo mes del año anterior."),
]


SERIES += [
    # --- EE.UU. desde FRED: llegan el mismo día de la publicación (las del Banco Central, con semanas de rezago)
    _simple("eeuu_fed_limite_superior", "Fed: tasa objetivo (límite superior)", "eeuu", lambda h: _raw(h, "eeuu_fed_limite_superior"), unidad="%",
            frecuencia="D", delta="pp", decimales=2, fuente="Reserva Federal (vía FRED)",
            definicion="Límite superior del rango objetivo de la tasa de fondos federales que fija la Fed en cada reunión del FOMC. El rango mide 0,25 puntos: "
                       "el límite inferior es 0,25 puntos menos. Es la tasa de política más influyente del mundo y mueve al dólar y al cobre."),
    _simple("eeuu_empleo_no_agricola", "EE.UU.: empleos creados en el mes (nómina no agrícola)", "eeuu",
            lambda h: _cambio_mensual_abs(_raw(h, "eeuu_empleo_no_agricola_nivel")), unidad="miles", delta="abs", polaridad="sube_bueno", firmado=True,
            decimales=0, sufijo=" mil", fuente="BLS (vía FRED)",
            definicion="Variación mensual del empleo no agrícola de Estados Unidos, en miles de puestos: el titular del reporte de empleo. Se revisa en los meses siguientes."),
    _simple("eeuu_ipp_demanda_final", "EE.UU.: IPP de demanda final interanual", "eeuu",
            lambda h: _yoy_fecha(_raw(h, "eeuu_ipp_demanda_final_indice")), unidad="%", delta="pp", polaridad="sube_malo", firmado=True,
            fuente="BLS (vía FRED)", definicion="Variación a 12 meses del índice de precios al productor de demanda final: el IPP que titulan los medios."),
    _simple("eeuu_pce_interanual", "EE.UU.: inflación PCE interanual", "eeuu", lambda h: _yoy_fecha(_raw(h, "eeuu_pce_indice")), unidad="%", delta="pp",
            polaridad="sube_malo", firmado=True, fuente="BEA (vía FRED)",
            definicion="Variación a 12 meses del índice de precios del gasto de consumo personal (PCE): la medida de inflación en que se basa la meta de 2% de la Fed."),
    _simple("eeuu_pib_trimestral", "EE.UU.: PIB real var. trimestral anualizada", "eeuu", lambda h: _raw(h, "eeuu_pib_real_anualizado"), unidad="%",
            frecuencia="T", delta="pp", polaridad="sube_bueno", firmado=True, fuente="BEA (vía FRED)",
            definicion="Crecimiento del PIB real de Estados Unidos contra el trimestre anterior, expresado a tasa anual (como lo reporta el BEA). Ojo: no es "
                       "comparable directo con el interanual de Chile."),
]


# Antigüedad máxima esperada del último dato (días desde su fecha) antes de considerar la serie "demorada".
# Se calcula como el peor caso entre dos publicaciones: la fecha de un dato es el día 1 de su mes, y el siguiente
# se publica cerca de 2 meses después (IPC ~día 8, IPP ~día 24, IMACEC 1er día hábil, ENE ~día 29, etc.) + margen.
MAX_DIAS_EXACTO = {
    "eeuu_desempleo": 75, "eeuu_inflacion": 80, "eeuu_fed_limite_superior": 7, "eeuu_empleo_no_agricola": 75, "eeuu_ipp_demanda_final": 80, "eeuu_pce_interanual": 100, "eeuu_pib_trimestral": 210, "eeuu_ipp": 110, "eeuu_pib_total": 210, "eeuu_pib_per_capita": 800,
    "eeuu_gini": 1500, "chile_gini": 1500, "chile_poblacion": 800, "chile_pib_per_capita_ppa": 800,
    "pib_chile": 245, "pib_real": 245, "pib_no_minero": 245, "pib_deflactor": 245, "pib_mineria": 180, "tpm_real": 80,
    "ipsa_indice_real": 7, "sp500": 7, "vix": 7, "tipo_cambio": 7, "tpm": 7,
}
MAX_DIAS_POR_SERIE = {
    "imacec": 100, "ipc": 80, "ipp": 92, "eee": 45, "eof": 45, "desempleo": 97, "remuneraciones": 97,
    "masa_salarial": 97, "exportaciones": 80, "importaciones": 80, "balanza": 80, "cobre_precio_promedio": 75, "cobre_precio_interanual": 75, "cobre": 7, "pib_real": 245, "tipo_cambio": 7, "ipsa": 7, "sp500": 7, "vix": 7, "tpm": 7,
    "pib_tendencia": 100, "inflacion_deflactor": 245, "pib_mineria": 180, "pib_no_minero": 245,
    "fuerza_trabajo": 97, "ocupados": 97, "desocupados": 97,
}


def _max_dias(spec_id: str) -> int:
    if spec_id in MAX_DIAS_EXACTO:
        return MAX_DIAS_EXACTO[spec_id]
    for prefijo, dias in MAX_DIAS_POR_SERIE.items():
        if spec_id.startswith(prefijo):
            return dias
    return 100


# Cuántos puntos llevan las mini-series de las tarjetas (≈3 años mensuales, ≈6 meses diarios)
PUNTOS_MINI = {"M": 36, "T": 16, "D": 130, "A": 20}


def _redondear(v: float) -> float:
    return round(float(v), 4)


def _filas(df: pd.DataFrame, huecos_dias: int | None = None) -> list[list]:
    """[fecha, valor]. Con `huecos_dias`, entre dos datos más separados que eso se intercala un null para que el
    gráfico corte la línea en vez de unir con una recta dos fechas que no tienen datos entre medio."""
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["valor"])
    filas, anterior = [], None
    for f, v in zip(df["fecha"], df["valor"]):
        if huecos_dias and anterior is not None and (f - anterior).days > huecos_dias:
            filas.append([(anterior + (f - anterior) / 2).strftime("%Y-%m-%d"), None])
        filas.append([f.strftime("%Y-%m-%d"), _redondear(v)])
        anterior = f
    return filas


def _etiqueta_periodo(fecha: pd.Timestamp, frecuencia: str) -> str:
    if frecuencia == "M":
        return f"{MESES_CORTOS[fecha.month - 1]} {fecha.year}"
    if frecuencia == "T":
        return f"T{(fecha.month - 1) // 3 + 1} {fecha.year}"
    if frecuencia == "A":
        return str(fecha.year)
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
    return "barras" if spec["id"].endswith(("_mensual", "_trimestral")) else "linea"


def _resumen(spec: dict, df: pd.DataFrame) -> dict:
    frecuencia = spec["frecuencia"]
    ultimo, previo = df.iloc[-1], (df.iloc[-2] if len(df) > 1 else None)
    delta = None
    if previo is not None:
        if spec["delta"] in ("pp", "abs"):
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
        "alerta": spec.get("alerta", True),
        "prefijo": spec.get("prefijo", ""),
        "sufijo": spec.get("sufijo", ""),
        "definicion": spec["definicion"],
        "ultimo": {"fecha": ultimo["fecha"].strftime("%Y-%m-%d"), "valor": _redondear(ultimo["valor"]),
                   "etiqueta": _etiqueta_periodo(ultimo["fecha"], frecuencia)},
        "previo": None if previo is None else {
            "fecha": previo["fecha"].strftime("%Y-%m-%d"), "valor": _redondear(previo["valor"]),
            "etiqueta": _etiqueta_periodo(previo["fecha"], frecuencia)},
        "delta": None if delta is None else _redondear(delta),
        "tono": _tono(delta, spec["polaridad"], 0.05),
        "mini": _filas(df.tail(PUNTOS_MINI.get(frecuencia, 36)), spec.get("huecos")),
    }


# Series del Monitor -> series de historico.csv cuyas revisiones explican cambios en ellas (ver data/revisiones.csv).
# unidad: cómo mostrar el valor revisado.
REVISIONES_DE = {
    "imacec_interanual": [("imacec", "")], "imacec_minero_interanual": [("imacec_minero", "")],
    "imacec_no_minero_interanual": [("imacec_no_minero", "")], "imacec_sa_mensual": [("imacec_sa", "")],
    "imacec_acumulado_anio": [("imacec", "")], "imacec_anio_movil": [("imacec", "")],
    "ipc_mensual": [("ipc_variacion_mensual", "%")], "ipc_acumulado_anio": [("ipc_indice", "")],
    "ipc_interanual": [("ipc_v12", "%")], "ipc_sin_volatiles_interanual": [("ipc_sin_volatiles_v12", "%")],
    "ipp_interanual": [("ipp_general", "")], "ipp_mensual": [("ipp_general", "")], "ipp_acumulado_anio": [("ipp_general", "")],
    "pib_real_interanual": [("pib_real", "")], "pib_real_trimestral": [("pib_real_sa", "")],
    "imacec_minero_sa_mensual": [("imacec_minero_sa", "")], "imacec_no_minero_sa_mensual": [("imacec_no_minero_sa", "")],
    "ocupados_interanual": [("ocupados", "")], "desocupados_interanual": [("desocupados", "")], "fuerza_trabajo_interanual": [("fuerza_trabajo", "")],
    "importaciones_mensual": [("importaciones_bienes", "")], "importaciones_interanual": [("importaciones_bienes", "")],
    "ipp_mineria_mensual": [("ipp_mineria", "")], "ipp_manufactura_mensual": [("ipp_manufactura", "")], "ipp_ega_mensual": [("ipp_ega", "")],
    "remuneraciones_real_mensual": [("remuneraciones_real", "")], "remuneraciones_nominal_mensual": [("remuneraciones_nominal", "")],
    "remuneraciones_nominal_interanual": [("remuneraciones_nominal", "")], "desempleo": [("desempleo", "%")],
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
    "ipp_general": "ipp_mensual",
    "pib_chile": "pib_real_interanual",
}


def _mes_desplazado(anio: int, mes: int, delta: int) -> tuple[int, int]:
    indice = anio * 12 + (mes - 1) + delta
    return indice // 12, indice % 12 + 1


def _texto_fed(h: pd.DataFrame, fecha: date) -> str | None:
    """Rango objetivo de la Fed después de la reunión y si cambió, ej. «3,75%–4,00% (+0,25 pp)»."""
    sup, inf = _raw(h, "eeuu_fed_limite_superior"), _raw(h, "eeuu_fed_limite_inferior")
    corte = pd.Timestamp(fecha)
    despues_s, despues_i = sup[sup["fecha"] > corte].head(1), inf[inf["fecha"] > corte].head(1)
    antes_s = sup[sup["fecha"] <= corte].tail(1)
    if despues_s.empty or despues_i.empty:
        return None
    fmt = lambda v: f"{v:.2f}".replace(".", ",") + "%"  # noqa: E731
    rango = f"{fmt(despues_i['valor'].iloc[0])}–{fmt(despues_s['valor'].iloc[0])}"
    if antes_s.empty:
        return rango
    cambio = despues_s["valor"].iloc[0] - antes_s["valor"].iloc[0]
    if abs(cambio) < 1e-9:
        return f"{rango} (sin cambios)"
    return f"{rango} ({'+' if cambio > 0 else '−'}{abs(cambio):.2f} pp)".replace(".", ",")


def construir_calendario(h: pd.DataFrame, hoy: date, resumenes: list[dict]) -> dict:
    """Últimas publicaciones y próximas de Chile y EE.UU., mezclando mes anterior, actual y siguiente. El valor que se muestra es el
    del PERÍODO de cada evento (no el último disponible de la serie): si no, un evento viejo mostraría el dato de un mes posterior."""
    meses = tuple(_mes_desplazado(hoy.year, hoy.month, d) for d in (-1, 0, 1))
    eventos = []
    for anio, mes in meses:
        for e in calendario_del_mes(anio, mes, h, hoy):
            estado = "cargado" if e["cargado"] else "pendiente" if e["fecha"] > hoy else "hoy" if e["fecha"] == hoy else "sin_cargar"
            eventos.append({
                "fecha": e["fecha"], "indicador": e["indicador"], "aproximado": e["aproximado"], "estado": estado,
                "tarjeta": TARJETA_DE_EVENTO.get(e["serie_dato"]), "periodo": e["periodo"], "pais": "CL", "tipo": e["serie_dato"],
            })
    eventos += eventos_eeuu(h, hoy, meses)
    eventos.sort(key=lambda e: (e["fecha"], e["pais"]))

    por_id = {r["id"]: r for r in resumenes}

    def valor_del_evento(e: dict) -> dict:
        resumen = por_id.get(e["tarjeta"])
        if e["estado"] != "cargado" or resumen is None:
            return {}
        if e.get("tipo") == "fomc":
            texto = _texto_fed(h, e["fecha"])
            return {"texto_valor": texto, "etiqueta": None} if texto else {}
        mini = resumen["mini"]
        if e["periodo"] is not None:
            clave = e["periodo"] if isinstance(e["periodo"], str) else e["periodo"].isoformat()
            punto = next(((f, v) for f, v in mini if f == clave and v is not None), None)
        else:  # series diarias (TPM): el primer dato desde la fecha del evento
            punto = next(((f, v) for f, v in mini if f >= e["fecha"].isoformat() and v is not None), None)
        if punto is None:
            return {}
        return {"valor": punto[1], "etiqueta": _etiqueta_periodo(pd.Timestamp(punto[0]), resumen["frecuencia"])}

    salida = [
        {"fecha": e["fecha"].isoformat(), "indicador": e["indicador"], "aproximado": e["aproximado"], "estado": e["estado"],
         "tarjeta": e["tarjeta"], "pais": e["pais"], **valor_del_evento(e)}
        for e in eventos
    ]
    pasados = [e for e in salida if e["fecha"] <= hoy.isoformat()][-14:]
    futuros = [e for e in salida if e["fecha"] > hoy.isoformat()][:18]
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
                "prefijo": spec.get("prefijo", ""), "sufijo": spec.get("sufijo", ""), "meta": spec.get("meta"), "revisiones": _revisiones_de(spec["id"], revisiones),
                "datos": _filas(df, spec.get("huecos")),
            },
        )

    disponibles = {r["id"] for r in resumenes}

    graficos = []
    for g in GRAFICOS:
        try:
            carga = g["build"](h)
        except Exception as error:  # un gráfico que falla no debe tumbar el resto del Monitor
            print(f"  (gráfico {g['id']} falló: {type(error).__name__}: {error})")
            carga = None
        if not carga:
            print(f"  (sin datos para el gráfico {g['id']}, se omite)")
            continue
        cabecera = {k: g[k] for k in ("id", "nombre", "tipo", "definicion", "unidad", "decimales", "frecuencia")}
        cabecera["meta"] = g.get("meta")
        cabecera["enlace"] = g.get("enlace")
        _escribir(SALIDA / "graficos" / f"{g['id']}.json", {**cabecera, **carga})
        graficos.append({**{k: cabecera[k] for k in ("id", "nombre", "tipo", "definicion", "frecuencia", "enlace")}, "pestana": g["pestana"]})
    ids_graficos = {g["id"] for g in graficos}

    temas = []
    for tema in TEMAS:
        if tema["serie"] not in disponibles:
            continue
        temas.append({**tema, "secundarias": [s for s in tema["secundarias"] if s in disponibles],
                      "graficos": [g for g in tema.get("graficos", []) if g in ids_graficos]})
    secciones = []
    for seccion in SECCIONES:
        secciones.append({**seccion, "series": [s for s in seccion.get("series", []) if s in disponibles],
                          "graficos": [g["id"] for g in graficos if g["pestana"] == seccion["id"]]})
    _escribir(SALIDA / "indice.json", {"temas": temas, "secciones": secciones, "graficos": graficos, "series": resumenes})

    try:
        for aviso in construir_composicion():
            print(f"  (composición: {aviso})")
    except Exception as error:  # la composición es una pestaña aparte: si falla no debe tumbar el resto del Monitor
        print(f"  (composición falló: {type(error).__name__}: {error})")

    if REVISIONES_PATH.exists():
        resumen_rev, mayores_rev = resumir_revisiones(pd.read_csv(REVISIONES_PATH), NOMBRES_SERIES)
        _escribir(SALIDA / "revisiones.json", {"resumen": resumen_rev.to_dict("records"), "mayores": mayores_rev.to_dict("records")})

    _escribir(SALIDA / "calendario.json", construir_calendario(h, hoy, resumenes))

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
