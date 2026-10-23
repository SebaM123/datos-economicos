"""Gráficos compuestos y secciones del Monitor (docs/monitor/data/graficos/*.json).

A diferencia de las series simples de exportar_monitor.SERIES (una tarjeta + una página de detalle),
acá van los gráficos que combinan varias series o que no son una serie de tiempo:

  lineas            varias líneas (ej. IPC total vs. subyacente)
  barras_apiladas   aporte de cada componente + línea del total (ej. contribuciones al IMACEC)
  proyeccion        histórico + proyección ARIMA con su banda de confianza
  ranking           barras horizontales comparando países o estados (Chile destacado)

La página los dibuja tal cual vienen: el cálculo vive acá, en Python, con las mismas funciones que
usa el dashboard de Streamlit.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from config import GINI_ESTADOS_PATH, OCDE_PAISES_PATH, PIB_ESTADOS_PATH
from proyecciones import (
    SERIES_PROYECTABLES,
    calcular_serie_interanual_imacec,
    calcular_serie_interanual_ipc,
    proyectar_serie,
)
from series_utils import (
    SECTORES_IMACEC,
    calcular_anio_movil,
    calcular_contribuciones_imacec,
    calcular_imacec_tendencia,
    calcular_interanual_mensual,
    calcular_ipc_componentes_interanual,
    calcular_masa_salarial_real,
    estado_mas_parecido_a_chile,
    obtener_serie,
)


COMPARADOR_DIR = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "comparador"


def _pares(df: pd.DataFrame) -> list[list]:
    df = df.replace([np.inf, -np.inf], np.nan).dropna(subset=["valor"])
    return [[f.strftime("%Y-%m-%d"), round(float(v), 4)] for f, v in zip(df["fecha"], df["valor"])]


def _serie(nombre: str, df: pd.DataFrame, **extra) -> dict:
    return {"nombre": nombre, "datos": _pares(df), **extra}


def _col(df: pd.DataFrame, columna: str) -> pd.DataFrame:
    return df[["fecha", columna]].rename(columns={columna: "valor"}).dropna().reset_index(drop=True)


def _raw(h: pd.DataFrame, serie: str) -> pd.DataFrame:
    return h[h["serie"] == serie][["fecha", "valor"]].sort_values("fecha").dropna().reset_index(drop=True)


# ---------- Actividad ----------
def _contribuciones_imacec(h):
    tabla = calcular_contribuciones_imacec(h)
    if tabla.empty:
        return None
    ancho = tabla.reset_index().rename(columns={"index": "fecha"})
    return {
        "series": [_serie(etq, _col(ancho, etq), color=color) for _, etq, color in SECTORES_IMACEC],
        "total": _serie("Total", _col(ancho, "total")),
    }


def _imacec_total_minero(h):
    return {"series": [
        _serie("Total", calcular_interanual_mensual(h, "imacec")),
        _serie("Minero", calcular_interanual_mensual(h, "imacec_minero")),
        _serie("No minero", calcular_interanual_mensual(h, "imacec_no_minero")),
    ]}


def _imacec_sa_niveles(h):
    return {"series": [
        _serie("Total", obtener_serie(h, "imacec_sa")),
        _serie("Minero", obtener_serie(h, "imacec_minero_sa")),
        _serie("No minero", obtener_serie(h, "imacec_no_minero_sa")),
    ]}


def _pib_tendencia(h):
    return {"series": [
        _serie("Año móvil 12 meses", calcular_imacec_tendencia(h, 12)),
        _serie("Tendencia 48 meses", calcular_imacec_tendencia(h, 48)),
        _serie("Año móvil 12 meses, per cápita", calcular_imacec_tendencia(h, 12, per_capita=True)),
        _serie("Tendencia 48 meses, per cápita", calcular_imacec_tendencia(h, 48, per_capita=True)),
    ]}


def _crecimiento_chile_ocde_mundo(h):
    """Crecimiento anual del PIB de Chile, la OCDE y el mundo (Banco Mundial, ver data_pipeline/fetch_comparador.py)."""
    ruta = COMPARADOR_DIR / "crecimiento_pib.json"
    if not ruta.exists():
        return None
    d = json.loads(ruta.read_text(encoding="utf-8"))
    series = []
    for codigo, nombre in (("CHL", "Chile"), ("OED", "OCDE"), ("WLD", "Mundo")):
        valores = d["datos"].get(codigo)
        if not valores:
            return None
        series.append({"nombre": nombre, "datos": [[f"{a}-01-01", v] for a, v in zip(d["anios"], valores) if v is not None]})
    return {"series": series}


# ---------- Precios ----------
def _ipc_subyacente(h):
    c = calcular_ipc_componentes_interanual(h)
    return {"series": [_serie(k, c[k]) for k in ("IPC total", "IPC subyacente (SAE: sin alimentos ni energía)", "IPC sin volátiles")]}


def _ipc_aperturas(h):
    c = calcular_ipc_componentes_interanual(h)
    return {"series": [_serie(k, c[k]) for k in ("Bienes sin volátiles", "Servicios sin volátiles", "Volátiles")]}


def _ipc_vs_deflactor(h):
    deflactor = _raw(h, "pib_deflactor")
    deflactor["valor"] = deflactor["valor"].pct_change(4) * 100
    return {"series": [_serie("IPC (mensual)", _raw(h, "ipc_v12")), _serie("Deflactor del PIB (trimestral)", deflactor.dropna())]}


def _ipp_sectores(periodos):
    def construir(h):
        series = []
        for nombre, clave in (("General industrias", "ipp_general"), ("Minería", "ipp_mineria"),
                              ("Industria manufacturera", "ipp_manufactura"), ("Electricidad, gas y agua", "ipp_ega")):
            df = _raw(h, clave)
            df["valor"] = df["valor"].pct_change(periodos) * 100
            series.append(_serie(nombre, df.dropna()))
        return {"series": series}
    return construir


# ---------- Empleo ----------
def _masa_salarial(h):
    masa = calcular_masa_salarial_real(h)
    if masa.empty:
        return None
    return {
        "series": [
            _serie("Remuneración real", _col(masa, "aporte_remuneracion"), color="#6c8cf0"),
            _serie("Empleo asalariado", _col(masa, "aporte_empleo"), color="#e0a83a"),
        ],
        "total": _serie("Masa salarial real", _col(masa, "interanual")),
    }


def _remuneraciones_inflacion(h):
    return {"series": [
        _serie("Remuneración nominal", calcular_interanual_mensual(h, "remuneraciones_nominal")),
        _serie("Remuneración real", calcular_interanual_mensual(h, "remuneraciones_real")),
        _serie("Inflación (IPC)", _raw(h, "ipc_v12")),
    ]}


def _desempleo_movil(h):
    d = _raw(h, "desempleo")
    return {"series": [_serie("Tasa mensual (trimestre móvil)", d), _serie("Promedio móvil 12 meses", calcular_anio_movil(d, operacion="mean"))]}


# ---------- Comercio exterior ----------
def _exportaciones_anio_movil(h):
    sectores = [("Minería", "exportaciones_mineria"), ("Agropecuario-silvícola-pesquero", "exportaciones_agropecuario"),
                ("Industrial", "exportaciones_industrial")]
    return {"series": [_serie(n, calcular_anio_movil(_raw(h, s))) for n, s in sectores]}


# ---------- Estados Unidos y desigualdad ----------
def _pib_pc_chile_eeuu(h):
    eeuu = _raw(h, "eeuu_pib_per_capita")
    eeuu["valor"] *= 1000  # viene en miles de USD; se lleva a USD para compararlo con Chile
    return {"series": [_serie("Chile", _raw(h, "chile_pib_per_capita_ppa")), _serie("Estados Unidos", eeuu)]}


def _gini_chile_eeuu(h):
    return {"series": [_serie("Chile", _raw(h, "chile_gini")), _serie("Estados Unidos", _raw(h, "eeuu_gini"))]}


def _num(v: float, decimales: int) -> str:
    """Número con separadores en español (punto de miles, coma decimal)."""
    return f"{v:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _ranking_estados(ruta, clave_valor, serie_chile, decimales, prefijo, h):
    if not ruta.exists():
        return None
    estados = json.loads(ruta.read_text(encoding="utf-8"))
    chile = _raw(h, serie_chile)
    if not estados or chile.empty:
        return None
    valor_chile, anio_chile = float(chile["valor"].iloc[-1]), int(chile["fecha"].iloc[-1].year)
    filas = [{"nombre": d["nombre"], "valor": round(float(d[clave_valor]), decimales), "anio": str(d["anio"])} for d in estados.values()]
    filas.append({"nombre": "Chile", "valor": round(valor_chile, decimales), "anio": str(anio_chile), "destacado": True})
    cercano = estado_mas_parecido_a_chile(estados, valor_chile, clave_valor=clave_valor)
    callout = None
    if cercano:
        _, d = cercano
        callout = (f"El estado de EE.UU. más parecido a Chile es {d['nombre']} ({prefijo}{_num(d[clave_valor], decimales)}, "
                   f"{d['anio']}); Chile: {prefijo}{_num(valor_chile, decimales)} ({anio_chile}).")
    return {"filas": filas, "callout": callout}


def _pib_estados(h):
    return _ranking_estados(PIB_ESTADOS_PATH, "pib_per_capita_usd", "chile_pib_per_capita_ppa", 0, "US$", h)


def _gini_estados(h):
    return _ranking_estados(GINI_ESTADOS_PATH, "gini", "chile_gini", 1, "", h)


# ---------- OCDE ----------
def _ocde(clave):
    def construir(h):
        if not OCDE_PAISES_PATH.exists():
            return None
        datos = json.loads(OCDE_PAISES_PATH.read_text(encoding="utf-8")).get(clave)
        if not datos:
            return None
        return {"filas": [{"nombre": i["nombre"], "valor": i["valor"], "anio": str(i["anio"]), "destacado": cod == "CHL"} for cod, i in datos.items()]}
    return construir


# ---------- Proyecciones ----------
def _proyeccion(clave):
    _titulo, funcion_historico, _nota = SERIES_PROYECTABLES[clave]

    def construir(h):
        historico = funcion_historico(h)
        if historico is None or historico.empty:
            return None
        proy = proyectar_serie(historico)
        if proy is None:
            return None
        return {
            "series": [_serie("Histórico", historico)],
            "proyeccion": {
                "nombre": "Proyección (ARIMA)",
                "datos": [[f.strftime("%Y-%m-%d"), round(float(v), 3), round(float(lo), 3), round(float(hi), 3)]
                          for f, v, lo, hi in zip(proy["fecha"], proy["valor"], proy["limite_inferior"], proy["limite_superior"])],
                "banda": "Intervalo de confianza (80%)",
            },
        }
    return construir


NOTA_OCDE = " Fuente: Banco Mundial, última cifra disponible de cada país."

def _nota_monitor(nota: str) -> str:
    """Las notas de proyecciones.py hablan de «secciones» del dashboard de Streamlit; en el Monitor son tarjetas de esta misma pestaña."""
    return (nota.replace("de la sección Inflación", "(tarjeta de arriba)")
                .replace("ver 'Expectativa PIB' (EEE) en la sección Actividad Económica", "ver las tarjetas de expectativa de crecimiento (EEE) de arriba")
                .replace("lo que buscás", "lo que se busca"))


# Catálogo. `pestana` es el id del tema o sección donde se muestra (ver exportar_monitor.TEMAS / SECCIONES).
GRAFICOS = [
    dict(id="crecimiento_chile_ocde_mundo", pestana="actividad", tipo="lineas", nombre="Crecimiento del PIB: Chile vs. OCDE y el mundo",
         unidad="%", decimales=1, frecuencia="A", build=_crecimiento_chile_ocde_mundo,
         enlace={"texto": "Comparar con otros países en el Comparador →", "hash": "#/comparador"},
         definicion="Variación anual del PIB real, datos anuales del Banco Mundial (pueden diferir un poco de las cifras del Banco Central, "
                    "porque están armonizados entre países). «OCDE» y «Mundo» son los agregados de esa misma fuente."),
    dict(id="contribuciones_imacec", pestana="actividad", tipo="barras_apiladas", nombre="Qué sector explica el crecimiento del IMACEC",
         unidad="pp", decimales=1, frecuencia="M", build=_contribuciones_imacec,
         definicion="Cuánto aportó (o restó) cada sector, en puntos porcentuales, a la variación interanual del IMACEC; la línea es "
                    "el total y es la suma de los seis sectores. Fuente: contribuciones publicadas por el Banco Central (base 2018)."),
    dict(id="imacec_total_minero", pestana="actividad", tipo="lineas", nombre="IMACEC total, minero y no minero (variación interanual)",
         unidad="%", decimales=1, frecuencia="M", build=_imacec_total_minero,
         definicion="Variación interanual del IMACEC total y separado en minero y no minero: sirve para ver si la actividad "
                    "depende del cobre o si el resto de la economía anda bien."),
    dict(id="imacec_sa_niveles", pestana="actividad", tipo="lineas", nombre="IMACEC desestacionalizado (índice 2018=100)",
         unidad="índice", decimales=1, frecuencia="M", build=_imacec_sa_niveles,
         definicion="Serie ajustada por el Banco Central para quitar el patrón estacional (verano, fiestas): permite comparar un mes "
                    "contra el anterior. La variación interanual, en cambio, usa la serie original."),
    dict(id="pib_tendencia", pestana="actividad", tipo="lineas", nombre="Crecimiento del PIB (vía IMACEC): tendencia y per cápita",
         unidad="%", decimales=1, frecuencia="M", build=_pib_tendencia,
         definicion="Variación interanual del IMACEC suavizado con el promedio de los últimos 12 (o 48) meses: muestra la tendencia de "
                    "fondo sin el ruido mes a mes. Las versiones per cápita dividen por la población de Chile (Banco Mundial, anual, "
                    "interpolada a mensual) para separar cuánto del crecimiento es más población y cuánto más producto por persona. "
                    "El IMACEC es un proxy mensual del PIB, no el PIB trimestral oficial."),
    dict(id="ipc_subyacente", pestana="precios", tipo="lineas", nombre="IPC total y medidas subyacentes (variación interanual)",
         unidad="%", decimales=1, frecuencia="M", meta=3, build=_ipc_subyacente,
         definicion="El IPC total incluye todo; las medidas subyacentes quitan lo más volátil para ver la tendencia de fondo: SAE excluye "
                    "alimentos y energía, «sin volátiles» excluye además otros componentes de precio muy cambiante. La línea punteada es "
                    "la meta del Banco Central (3%)."),
    dict(id="ipc_aperturas", pestana="precios", tipo="lineas", nombre="Bienes, servicios y volátiles (variación interanual)",
         unidad="%", decimales=1, frecuencia="M", meta=3, build=_ipc_aperturas,
         definicion="Permite ver si la inflación de fondo viene de los bienes (más ligada al dólar) o de los servicios (más ligada a "
                    "salarios). Variaciones anuales oficiales del Banco Central/INE."),
    dict(id="ipc_vs_deflactor", pestana="precios", tipo="lineas", nombre="Inflación: IPC vs. deflactor del PIB",
         unidad="%", decimales=1, frecuencia="M", build=_ipc_vs_deflactor,
         definicion="El deflactor cubre TODO lo que produce el país (incluye bienes de inversión y exportaciones), no solo lo que compran "
                    "los hogares, y suele reaccionar más al precio del cobre. El IPC es mensual; el deflactor, trimestral."),
    dict(id="ipp_sectores_interanual", pestana="precios", tipo="lineas", nombre="IPP por sector (variación interanual)",
         unidad="%", decimales=1, frecuencia="M", build=_ipp_sectores(12),
         definicion="Cuánto suben en 12 meses los precios que reciben los productores, en total y por sector. La minería (cobre) es la que "
                    "más mueve el índice general."),
    dict(id="ipp_sectores_mensual", pestana="precios", tipo="lineas", nombre="IPP por sector (variación mensual)",
         unidad="%", decimales=1, frecuencia="M", build=_ipp_sectores(1),
         definicion="Variación de un mes contra el anterior, que es como el INE titula la publicación. Es mucho más volátil que la "
                    "interanual."),
    dict(id="masa_salarial_aportes", pestana="empleo", tipo="barras_apiladas", nombre="Masa salarial real (aprox.): aporte del salario y del empleo",
         unidad="pp", decimales=1, frecuencia="M", build=_masa_salarial,
         definicion="Aproximación propia, no oficial: índice real de remuneraciones (INE, por hora) x ocupados asalariados (ENE). No captura "
                    "cambios en las horas trabajadas. Sirve para ver cuánto del movimiento viene del salario real y cuánto del empleo."),
    dict(id="remuneraciones_inflacion", pestana="empleo", tipo="lineas", nombre="Remuneraciones nominales, reales e inflación (variación interanual)",
         unidad="%", decimales=1, frecuencia="M", build=_remuneraciones_inflacion,
         definicion="Cuánto crecen los sueldos en pesos (nominal), cuánto en poder de compra (real) y cuánto suben los precios."),
    dict(id="desempleo_movil", pestana="empleo", tipo="lineas", nombre="Desempleo: tasa y promedio móvil de 12 meses",
         unidad="%", decimales=1, frecuencia="M", build=_desempleo_movil,
         definicion="El promedio de los últimos 12 meses suaviza el ruido mes a mes para ver la tendencia de fondo (acá se promedia, "
                    "no se suma: sumar una tasa no tiene interpretación)."),
    dict(id="exportaciones_sectores_anio_movil", pestana="comercio", tipo="lineas", nombre="Exportaciones por sector, año móvil (millones de US$)",
         unidad="US$ MM", decimales=0, frecuencia="M", build=_exportaciones_anio_movil,
         definicion="Suma de los últimos 12 meses, recalculada cada mes: quita la estacionalidad (por ejemplo, la fruta se exporta sobre todo "
                    "a fin de año) para ver la tendencia de fondo de cada sector."),
    dict(id="pib_pc_chile_eeuu", pestana="eeuu", tipo="lineas", nombre="PIB per cápita (PPA): Chile vs. Estados Unidos",
         unidad="US$", decimales=0, frecuencia="A", build=_pib_pc_chile_eeuu,
         definicion="Producto por persona en dólares ajustados por paridad de poder de compra, misma fuente y metodología (FMI-WEO vía "
                    "Banco Central), incluye proyecciones del FMI."),
    dict(id="pib_estados_eeuu", pestana="eeuu", tipo="ranking", nombre="PIB per cápita por estado de EE.UU. (y Chile como referencia)",
         unidad="US$", decimales=0, frecuencia="A", build=_pib_estados,
         definicion="Referencia aproximada: PIB real por estado en dólares encadenados (FRED), no ajustado por paridad de poder de compra "
                    "como el dato de Chile; las magnitudes no son directamente comparables, pero sirven para ubicar el orden de tamaño."),
    dict(id="gini_chile_eeuu", pestana="desigualdad", tipo="lineas", nombre="Índice de Gini: Chile vs. Estados Unidos",
         unidad="índice", decimales=1, frecuencia="A", build=_gini_chile_eeuu,
         definicion="Mide la desigualdad de ingresos entre 0 (igualdad perfecta) y 100 (un solo hogar concentra todo). Banco Mundial, serie "
                    "anual con huecos (viene de encuestas de hogares)."),
    dict(id="gini_estados_eeuu", pestana="desigualdad", tipo="ranking", nombre="Índice de Gini por estado de EE.UU. (y Chile como referencia)",
         unidad="índice", decimales=1, frecuencia="A", build=_gini_estados,
         definicion="Fuente: Census Bureau, estimaciones ACS de 5 años. Mismo concepto que el Gini de Chile (Banco Mundial) pero de una "
                    "fuente distinta: sirve para ubicar el orden de magnitud entre estados, no para una comparación exacta."),
]
# Textos propios del Monitor (los de config.OCDE_INDICADORES hacen referencia a otras secciones del dashboard de Streamlit).
TEXTOS_OCDE = {
    "pib_per_capita_ppa": ("PIB per cápita, PPA (USD internacionales)",
                           "Producto por persona ajustado por paridad de poder de compra. Metodología del Banco Mundial: los niveles pueden no calzar "
                           "exacto con la serie de Chile del FMI que se muestra en Actividad, pero sirven para ubicar a Chile entre sus pares."),
    "desempleo": ("Tasa de desempleo (%)",
                  "Estimación armonizada de la OIT (Organización Internacional del Trabajo), vía Banco Mundial. No es la tasa que publica el INE "
                  "(la que se usa en Empleo): está armonizada para que los países sean comparables entre sí."),
    "inflacion": ("Inflación anual (%)", "Variación anual del índice de precios al consumidor, según el Banco Mundial."),
    "gini": ("Índice de Gini", "Desigualdad de ingresos entre 0 (igualdad perfecta) y 100 (un solo hogar concentra todo). Viene de encuestas de "
                               "hogares, por eso el año de la última cifra varía entre países."),
}
GRAFICOS += [
    dict(id=f"ocde_{clave}", pestana="ocde", tipo="ranking", nombre=titulo,
         unidad={"pib_per_capita_ppa": "US$", "desempleo": "%", "inflacion": "%", "gini": "índice"}[clave],
         decimales=0 if clave == "pib_per_capita_ppa" else 1, frecuencia="A", build=_ocde(clave), definicion=definicion + NOTA_OCDE)
    for clave, (titulo, definicion) in TEXTOS_OCDE.items()
]
GRAFICOS += [
    dict(id=f"proyeccion_{clave}", pestana="proyecciones", tipo="proyeccion", nombre=titulo, unidad="%", decimales=1, frecuencia="M",
         build=_proyeccion(clave), definicion=_nota_monitor(nota))
    for clave, (titulo, _f, nota) in SERIES_PROYECTABLES.items()
]
