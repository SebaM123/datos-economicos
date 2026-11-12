"""Lectura y cálculo con las matrices insumo-producto (MIP) del Banco Central de Chile, a 111 actividades.

Las MIP vienen en tres compilaciones de cuentas nacionales (base 2008: 2008-2013; base 2013: 2013-2017; base 2018: 2018-2023). La clasificación de 111 actividades es la
misma en las tres (mismos códigos), así que se usa esa para toda la serie; los 12 sectores difieren entre la base 2008 y las demás, por eso los 12 sectores de este módulo
se arman agrupando las 111 (ver GRUPOS_12).

Cada libro trae la matriz «doméstica a precio básico, actividad por actividad» (consumo intermedio de producción nacional) con la demanda final por componente, y debajo las filas de
importaciones, impuestos, valor agregado (remuneraciones y excedente) y producción. Con eso:
  A = Z / X (coeficientes técnicos), L = (I - A)^-1 (inversa de Leontief),
  multiplicador de producción de j = suma de la columna j de L; de valor agregado = v' L e_j (v = valor agregado / producción); etc.
La contabilidad se comprueba en cada año: fila (consumo intermedio + demanda final = producción) y columna (insumos + importaciones + impuestos + valor agregado = producción).
"""

import re
from pathlib import Path

import numpy as np
import openpyxl

N = 111
# Demanda final: texto del encabezado -> clave
DEMANDA = {"consumo de hogares": "hogares", "consumo  de ipsfl": "ipsfl", "consumo de ipsfl": "ipsfl", "consumo de gobierno": "gobierno", "formación bruta": "fbcf",
           "variación de existencias": "existencias", "exportaciones": "exportaciones"}
FILAS = {"importaciones": "imp", "impuestos sobre productos": "imp_prod", "derechos de importación": "derechos", "valor agregado": "va", "remuneraciones": "rem",
         "excedente": "eeb", "impuestos netos": "imp_netos", "producción": "x"}
# 12 sectores comparables en toda la serie (los de la base 2013 y 2018), como grupos de los códigos de 111 actividades
GRUPOS_12 = [
    ("Agropecuario-silvícola y pesca", range(1, 13)), ("Minería", range(13, 19)), ("Industria manufacturera", range(19, 64)), ("Electricidad, gas, agua y desechos", range(64, 70)),
    ("Construcción", range(70, 74)), ("Comercio, hoteles y restaurantes", range(74, 79)), ("Transporte, comunicaciones e información", range(79, 94)),
    ("Intermediación financiera", range(94, 97)), ("Servicios inmobiliarios y de vivienda", range(97, 99)), ("Servicios empresariales", range(99, 104)),
    ("Servicios personales (educación, salud y otros)", range(105, 112)), ("Administración pública", range(104, 105)),
]
# Focos del análisis (códigos de las 111 actividades)
FOCOS = {
    "cobre": {"nombre": "Cobre", "sectores": [15], "extra": [57]},  # 57 = metales no ferrosos (cobre refinado y otros): se muestra aparte
    "forestal": {"nombre": "Cadena forestal", "sectores": [10, 39, 40, 41, 42, 43]},
}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s).strip().lower())


def leer_hoja(ws) -> dict:
    """Lee una hoja de MIP a 111 actividades. Devuelve Z (N×N), demanda final por componente y los vectores por actividad (columna)."""
    filas = list(ws.iter_rows(values_only=True))
    # fila de encabezados de demanda final
    hdr = next(i for i, r in enumerate(filas) if any(isinstance(v, str) and _norm(v) == "consumo de hogares" for v in r))
    cols_fd = {}
    for j, v in enumerate(filas[hdr]):
        if isinstance(v, str):
            for k, clave in DEMANDA.items():
                if _norm(v).startswith(k.strip()) and clave not in cols_fd:
                    cols_fd[clave] = j
    # sectores: filas cuya etiqueta (col 1) es el número 1..111, tomando el primer bloque
    ini = next(i for i, r in enumerate(filas) if i > hdr and str(r[1]).strip() == "1")
    Z = np.array([[float(v or 0) for v in filas[ini + k][2:2 + N]] for k in range(N)])
    for k in range(N):
        assert str(filas[ini + k][1]).strip() == str(k + 1), f"sector {k + 1} fuera de lugar"
    fd = {clave: np.array([float(filas[ini + k][j] or 0) for k in range(N)]) for clave, j in cols_fd.items()}
    vec = {}
    for r in filas[ini + N:ini + N + 25]:
        etiqueta = _norm(r[1]) if isinstance(r[1], str) else ""
        for k, clave in FILAS.items():
            if etiqueta.startswith(k) and clave not in vec and sum(isinstance(v, (int, float)) for v in r[2:2 + N]) >= 50:  # hay filas con celdas vacías (= 0)
                vec[clave] = np.array([float(v or 0) for v in r[2:2 + N]])
    faltan = [c for c in ("imp", "va", "rem", "x") if c not in vec] + [c for c in ("exportaciones", "hogares", "gobierno", "fbcf") if c not in fd]
    assert not faltan, f"faltan {faltan}"
    return {"Z": Z, "fd": fd, "vec": vec}


def validar(d: dict) -> dict:
    """Errores relativos máximos de las dos identidades contables."""
    Z, fd, v = d["Z"], d["fd"], d["vec"]
    x = v["x"]
    fila = Z.sum(axis=1) + sum(fd.values())
    col = Z.sum(axis=0) + v["imp"] + v.get("imp_prod", 0) + v.get("derechos", 0) + v["va"]
    ok = x > 1e-9
    return {"fila": float(np.max(np.abs(fila - x)[ok] / x[ok])), "col": float(np.max(np.abs(col - x)[ok] / x[ok]))}


def coeficientes(d: dict):
    x = d["vec"]["x"]
    xs = np.where(x > 1e-9, x, 1.0)
    A = d["Z"] / xs[None, :]
    L = np.linalg.inv(np.eye(len(x)) - A)
    return A, L


def indicadores(d: dict) -> dict:
    """Multiplicadores, encadenamientos y contenido de las exportaciones para un año."""
    A, L = coeficientes(d)
    x, va, rem, imp = d["vec"]["x"], d["vec"]["va"], d["vec"]["rem"], d["vec"]["imp"]
    xs = np.where(x > 1e-9, x, 1.0)
    v, r, m = va / xs, rem / xs, imp / xs
    e = d["fd"]["exportaciones"]
    fd_total = sum(d["fd"].values())
    mult_x, mult_va, mult_rem, mult_imp = L.sum(axis=0), v @ L, r @ L, m @ L
    bl = mult_x / mult_x.mean()
    fl = L.sum(axis=1) / L.sum(axis=1).mean()  # sensibilidad de dispersión (hacia adelante)
    return {"A": A, "L": L, "v": v, "r": r, "m": m, "x": x, "e": e, "fd_total": fd_total, "mult_x": mult_x, "mult_va": mult_va, "mult_rem": mult_rem, "mult_imp": mult_imp,
            "bl": bl, "fl": fl}


def efecto_demanda(ind: dict, dfd: np.ndarray) -> dict:
    """Efecto de un cambio en la demanda final (vector de 111, misma unidad que X) sobre producción, valor agregado, remuneraciones e importaciones."""
    dx = ind["L"] @ dfd
    return {"dx": dx, "dva": ind["v"] * dx, "drem": ind["r"] * dx, "dimp": ind["m"] * dx}


def agregar_12(d: dict) -> dict:
    """Matriz agregada a 12 sectores (suma de Z, de los vectores y de la demanda final)."""
    G = np.zeros((12, N))
    for g, (_, cods) in enumerate(GRUPOS_12):
        for c in cods:
            G[g, c - 1] = 1
    out = {"Z": G @ d["Z"] @ G.T, "fd": {k: G @ x for k, x in d["fd"].items()}, "vec": {k: G @ x for k, x in d["vec"].items()}}
    return out


def abrir(path: Path, hoja: str):
    wb = openpyxl.load_workbook(path, data_only=True)
    return wb[hoja]
