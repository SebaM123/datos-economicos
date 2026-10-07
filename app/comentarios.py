"""Comentarios automáticos, generados con PLANTILLAS (no con un modelo de
lenguaje): cada función arma una o dos oraciones a partir de los mismos
cálculos que ya existen en series_utils.py, con lógica fija (if/else sobre
subió/bajó, comparación contra el mes/trimestre anterior, etc.).

Deliberadamente NO se usa un LLM acá: esta sección se publica sola, sin
revisión humana antes de salir a producción (corre en el mismo GitHub
Actions diario que actualiza los datos), así que conviene que el texto sea
100% determinístico y trazable a un cálculo verificable -- ver
feedback_no_publicar_datos_dudosos en las decisiones de este proyecto.
"""

import pandas as pd

from series_utils import (
    calcular_desempleo_interanual,
    calcular_imacec_interanual,
    calcular_inflacion_acumulada_anual,
    calcular_inflacion_interanual,
    calcular_inflacion_subyacente_interanual,
    calcular_tpm_real,
)

MESES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _nombre_mes(fecha: pd.Timestamp) -> str:
    return MESES[fecha.month - 1]


def _direccion(valor: float, umbral: float = 0.05) -> str:
    if valor > umbral:
        return "subió"
    if valor < -umbral:
        return "bajó"
    return "se mantuvo prácticamente sin cambios"


def comentario_ipc(historico: pd.DataFrame) -> str | None:
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha")
    if ipc.empty:
        return None
    ultimo = ipc.iloc[-1]
    interanual = calcular_inflacion_interanual(historico)
    acumulada = calcular_inflacion_acumulada_anual(historico)

    partes = [
        f"El IPC de {_nombre_mes(ultimo['fecha'])} {_direccion(ultimo['valor'], umbral=0.0)} "
        f"{ultimo['valor']:+.1f}% respecto al mes anterior."
    ]
    if interanual:
        valor_ia, _ = interanual
        partes.append(f"Con eso, la inflación interanual (12 meses) quedó en {valor_ia:.1f}%.")
    subyacente = calcular_inflacion_subyacente_interanual(historico)
    if subyacente:
        valor_sub, _ = subyacente
        partes.append(f"La inflación subyacente (sin alimentos ni energía) es de {valor_sub:.1f}% interanual.")
    if acumulada:
        valor_ac, fecha_ac = acumulada
        partes.append(f"En lo que va de {fecha_ac.year}, los precios acumulan un alza de {valor_ac:.1f}%.")
    return " ".join(partes)


def comentario_imacec(historico: pd.DataFrame) -> str | None:
    interanual = calcular_imacec_interanual(historico)
    if interanual is None:
        return None
    valor, fecha = interanual

    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha")
    interanual_anterior = None
    if len(imacec) >= 14:
        anterior = imacec.iloc[-2]
        hace_un_anio_de_anterior = imacec.iloc[-14]
        interanual_anterior = (anterior["valor"] / hace_un_anio_de_anterior["valor"] - 1) * 100

    verbo = "creció" if valor > 0.05 else ("cayó" if valor < -0.05 else "se mantuvo sin cambios")
    frase = f"La actividad económica (IMACEC) de {_nombre_mes(fecha)} {verbo}"
    frase += f" {abs(valor):.1f}% en 12 meses." if abs(valor) > 0.05 else " en 12 meses."
    if interanual_anterior is not None:
        if valor > interanual_anterior + 0.05:
            frase += f" Mejora respecto al mes anterior ({interanual_anterior:+.1f}%)."
        elif valor < interanual_anterior - 0.05:
            frase += f" Empeora respecto al mes anterior ({interanual_anterior:+.1f}%)."
        else:
            frase += " Un ritmo similar al del mes anterior."

    # Aporte por sector (contribuciones oficiales del Banco Central, en pp), solo si están
    # al día para el mismo mes.
    def aporte(serie: str) -> float | None:
        fila = historico[(historico["serie"] == serie) & (historico["fecha"] == fecha)]
        return float(fila["valor"].iloc[0]) if not fila.empty else None

    c_minero = aporte("imacec_c_minero")
    otros = [aporte(s) for s in ("imacec_c_industria", "imacec_c_resto_bienes", "imacec_c_comercio",
                                 "imacec_c_servicios", "imacec_c_impuestos")]
    if c_minero is not None and all(o is not None for o in otros):
        resto = sum(otros)
        frase += (
            f" Por sector, la minería {'sumó' if c_minero >= 0 else 'restó'} {abs(c_minero):.1f} pp "
            f"y el resto de la economía {'sumó' if resto >= 0 else 'restó'} {abs(resto):.1f} pp."
        )
    return frase


def comentario_tpm(historico: pd.DataFrame) -> str | None:
    tpm = historico[historico["serie"] == "tpm"].sort_values("fecha")
    if tpm.empty:
        return None
    ultimo = tpm.iloc[-1]

    cambio_frase = "se mantuvo en"
    if len(tpm) >= 2:
        anterior = tpm.iloc[-2]
        if ultimo["valor"] > anterior["valor"] + 1e-9:
            cambio_frase = f"subió desde {anterior['valor']:.2f}% a"
        elif ultimo["valor"] < anterior["valor"] - 1e-9:
            cambio_frase = f"bajó desde {anterior['valor']:.2f}% a"
        else:
            cambio_frase = "se mantuvo en"

    frase = f"El Banco Central {cambio_frase} {ultimo['valor']:.2f}% en su última decisión."
    real = calcular_tpm_real(historico)
    if real:
        valor_real, _ = real
        postura = "restrictiva" if valor_real > 0.5 else ("expansiva" if valor_real < -0.5 else "prácticamente neutral")
        frase += f" Descontando la inflación, la TPM real ex-post es {valor_real:+.1f}pp — postura {postura}."
    return frase


def comentario_desempleo(historico: pd.DataFrame) -> str | None:
    desempleo = historico[historico["serie"] == "desempleo"].sort_values("fecha")
    if desempleo.empty:
        return None
    ultimo = desempleo.iloc[-1]
    interanual = calcular_desempleo_interanual(historico)

    frase = f"La tasa de desempleo llegó a {ultimo['valor']:.1f}%."
    if interanual:
        valor_ia, _ = interanual
        if valor_ia > 0.05:
            frase += f" Subió {valor_ia:.1f} puntos porcentuales respecto a hace un año."
        elif valor_ia < -0.05:
            frase += f" Bajó {abs(valor_ia):.1f} puntos porcentuales respecto a hace un año."
        else:
            frase += " Prácticamente igual que hace un año."
    return frase


# Registro de comentarios: clave -> (título, función, nombre de la fecha para mostrar)
COMENTARIOS = {
    "ipc": ("Inflación (IPC)", comentario_ipc, "ipc_variacion_mensual"),
    "imacec": ("Actividad económica (IMACEC)", comentario_imacec, "imacec"),
    "tpm": ("Tasa de Política Monetaria", comentario_tpm, "tpm"),
    "desempleo": ("Empleo", comentario_desempleo, "desempleo"),
}
