"""Matrices insumo-producto de Chile (Banco Central), 2008-2023: resumen para la pestaña «Insumo-producto» del Monitor (docs/monitor/data/mip.json).

Los datos son las MIP anuales «doméstica a precio básico» a 111 actividades que publica el Banco Central en https://www.bcentral.cl/web/banco-central/cuentas-nacionales-anuales-excel
(una por año y compilación: base 2008 para 2008-2013, base 2013 para 2013-2017 y base 2018 para 2018-2023). El sitio tiene protección anti-bot, así que los archivos se bajan a
mano en una carpeta y este script los lee; se renueva cuando el Banco Central publica un año nuevo (con unos 27 meses de rezago).

Uso:  python procesar_mip.py CARPETA
CARPETA debe contener los archivos con estos nombres (los del sitio antiguo y los nuevos): MIP_2008-2013_111x111.xlsx (hojas MIP_2008..MIP_2013), CdeR2013_MIP_111x111.xlsx,
2014_MIP_111x111.xlsx ... 2017_MIP_111x111.xlsx y MIP_2018_111x111.xlsx ... MIP_2023_111x111.xlsx (hoja «1» en los de base 2013 y 2018).

Qué calcula (ver mip_lib.py): coeficientes técnicos A = Z/X, inversa de Leontief L = (I - A)^-1, multiplicadores de producción, valor agregado, remuneraciones e importaciones,
encadenamientos hacia atrás y hacia adelante (Rasmussen-Hirschman), y para el cobre y la cadena forestal el valor agregado nacional que generan sus exportaciones (directo + indirecto).
Para el simulador guarda los coeficientes completos de 4 años (2008, 2013, 2018, 2023). Montos en miles de millones de pesos corrientes de cada año.
"""

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import openpyxl

import mip_lib as M

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "mip.json"
CASOS = ([(a, "MIP_2008-2013_111x111.xlsx", f"MIP_{a}", "2008") for a in range(2008, 2014)]  # el 2013 de la base 2008 solo sirve para medir el quiebre de base
         + [(2013, "CdeR2013_MIP_111x111.xlsx", "1", "2013")] + [(a, f"{a}_MIP_111x111.xlsx", "1", "2013") for a in range(2014, 2018)]
         + [(a, f"MIP_{a}_111x111.xlsx", "1", "2018") for a in range(2018, 2024)])
ANIOS_SIM = [2008, 2013, 2018, 2023]
R = lambda x, n=4: np.round(np.asarray(x, dtype=float), n).tolist()  # noqa: E731


def _nombres(path: Path) -> list[str]:
    ws = openpyxl.load_workbook(path, data_only=True)["Glosa"]
    nom = {}
    for r in ws.iter_rows(values_only=True):
        x = [str(c).strip() for c in r if c not in (None, "")]
        if len(x) >= 2 and x[0].isdigit():
            nom[int(x[0])] = x[1]
    return [nom[i] for i in range(1, M.N + 1)]


def _foco(d, ind, cods):
    """Valor agregado, remuneraciones e importaciones asociados a las exportaciones de un grupo de actividades, directos e indirectos."""
    e = np.zeros(M.N)
    idx = [c - 1 for c in cods]
    e[idx] = d["fd"]["exportaciones"][idx]
    exp_total = d["fd"]["exportaciones"].sum()
    if e.sum() <= 0:
        return None
    dx = ind["L"] @ e
    va_i = ind["v"] * dx
    G = np.zeros((12, M.N))
    for g, (_, cs) in enumerate(M.GRUPOS_12):
        for c in cs:
            G[g, c - 1] = 1
    return {
        "exportaciones": float(e.sum()), "pct_exportaciones": float(e.sum() / exp_total * 100),
        "va_total": float(va_i.sum()), "pct_va_pais": float(va_i.sum() / d["vec"]["va"].sum() * 100),
        "rem_total": float((ind["r"] * dx).sum()), "pct_rem_pais": float((ind["r"] * dx).sum() / d["vec"]["rem"].sum() * 100),
        "va_por_unidad": float(va_i.sum() / e.sum()), "imp_por_unidad": float((ind["m"] * dx).sum() / e.sum()),
        "va_directo_por_unidad": float((ind["v"][idx] * e[idx]).sum() / e.sum()),
        "prod_total": float(dx.sum()), "arrastre": float(dx.sum() / e.sum()),
        "va_por_sector12": R(G @ va_i, 3),
        "va_por_sector111": R(va_i, 3),
    }


def main(carpeta: Path) -> None:
    cache: dict = {}
    nombres = _nombres(carpeta / "MIP_2023_111x111.xlsx")
    anios, bases = [], []
    serie = {k: [] for k in ("x", "va", "rem", "imp", "exp", "mult_x", "mult_va", "mult_rem", "mult_imp", "bl", "fl")}
    s12 = {k: [] for k in ("x", "va", "rem", "imp", "exp", "mult_x", "mult_va", "mult_rem", "mult_imp", "bl", "fl")}
    focos = {k: {"nombre": v["nombre"], "sectores": v["sectores"], "anios": []} for k, v in M.FOCOS.items()}
    sim = {}
    escala = lambda base: 1e-3 if base == "2008" else 1.0  # la base 2008 viene en millones de pesos, el resto en miles de millones  # noqa: E731
    alt2013 = None
    for anio, archivo, hoja, base in CASOS:
        if archivo not in cache:
            cache[archivo] = openpyxl.load_workbook(carpeta / archivo, data_only=True)
        d = M.leer_hoja(cache[archivo][hoja])
        err = M.validar(d)
        if max(err.values()) > 1e-4:
            raise RuntimeError(f"{anio}: la matriz no cuadra {err}")
        k = escala(base)
        d["Z"] = d["Z"] * k
        d["fd"] = {n: v * k for n, v in d["fd"].items()}
        d["vec"] = {n: v * k for n, v in d["vec"].items()}
        ind = M.indicadores(d)
        if anio == 2013 and base == "2008":  # el 2013 existe en dos compilaciones: sirve para medir cuánto cambia la base
            alt2013 = {"mult_x": ind["mult_x"], "mult_va": ind["mult_va"], "bl": ind["bl"]}
            continue
        anios.append(anio); bases.append(base)
        for n, v in (("x", d["vec"]["x"]), ("va", d["vec"]["va"]), ("rem", d["vec"]["rem"]), ("imp", d["vec"]["imp"]), ("exp", d["fd"]["exportaciones"]),
                     ("mult_x", ind["mult_x"]), ("mult_va", ind["mult_va"]), ("mult_rem", ind["mult_rem"]), ("mult_imp", ind["mult_imp"]), ("bl", ind["bl"]), ("fl", ind["fl"])):
            serie[n].append(R(v, 1 if n in ("x", "va", "rem", "imp", "exp") else 4))
        d12 = M.agregar_12(d)
        i12 = M.indicadores(d12)
        for n, v in (("x", d12["vec"]["x"]), ("va", d12["vec"]["va"]), ("rem", d12["vec"]["rem"]), ("imp", d12["vec"]["imp"]), ("exp", d12["fd"]["exportaciones"]),
                     ("mult_x", i12["mult_x"]), ("mult_va", i12["mult_va"]), ("mult_rem", i12["mult_rem"]), ("mult_imp", i12["mult_imp"]), ("bl", i12["bl"]), ("fl", i12["fl"])):
            s12[n].append(R(v, 1 if n in ("x", "va", "rem", "imp", "exp") else 4))
        for fk, fv in M.FOCOS.items():
            f = _foco(d, ind, fv["sectores"])
            focos[fk]["anios"].append({"anio": anio, **(f or {})})
        if anio in ANIOS_SIM:
            fd = d["fd"]
            sim[str(anio)] = {
                "A": [[round(v, 5) if v else 0 for v in fila] for fila in ind["A"].tolist()], "v": R(ind["v"], 5), "r": R(ind["r"], 5), "m": R(ind["m"], 5), "x": R(d["vec"]["x"], 2),
                "fd": {"exportaciones": R(fd["exportaciones"], 2), "hogares": R(fd["hogares"], 2), "gobierno": R(fd["gobierno"], 2), "fbcf": R(fd["fbcf"], 2),
                       "otros": R(fd.get("ipsfl", 0) + fd.get("existencias", 0), 2)},
            }
        if anio in (2008, 2013, 2018, 2023):  # proveedores y clientes de las actividades focales
            for c in (15, 10, 41, 39, 40, 42):
                for fk in ("detalle",):
                    focos.setdefault("_detalle", {}).setdefault(str(c), {})[str(anio)] = {
                        "compra": [[int(j) + 1, round(float(ind["A"][j, c - 1]), 4)] for j in np.argsort(-ind["A"][:, c - 1])[:8]],  # cuánto compra de cada actividad por $ producido
                        "total": [[int(j) + 1, round(float(ind["L"][j, c - 1]), 4)] for j in np.argsort(-ind["L"][:, c - 1])[:8]],  # requerimiento total directo + indirecto
                        "vende": [[int(j) + 1, round(float(d["Z"][c - 1, j] / max(d["vec"]["x"][c - 1], 1e-9)), 4)] for j in np.argsort(-d["Z"][c - 1, :])[:8]],  # a quién le vende (parte de su producción)
                    }
    quiebre = None
    if alt2013 is not None:
        i13 = anios.index(2013)
        nuevo = {"mult_x": np.array(serie["mult_x"][i13]), "mult_va": np.array(serie["mult_va"][i13]), "bl": np.array(serie["bl"][i13])}
        quiebre = {"anio": 2013, "mult_x_dif_prom_abs": float(np.mean(np.abs(nuevo["mult_x"] - alt2013["mult_x"]))), "mult_x_dif_prom_rel": float(np.mean(np.abs(nuevo["mult_x"] / alt2013["mult_x"] - 1))),
                   "cobre": [float(alt2013["mult_x"][14]), float(nuevo["mult_x"][14])], "celulosa": [float(alt2013["mult_x"][40]), float(nuevo["mult_x"][40])],
                   "correlacion_mult_x": float(np.corrcoef(nuevo["mult_x"], alt2013["mult_x"])[0, 1])}
    salida = {
        "descargado": date.today().isoformat(), "fuente": "Banco Central de Chile, matrices insumo-producto anuales (doméstica a precio básico, 111 actividades)", "unidad": "miles de millones de pesos corrientes de cada año",
        "anios": anios, "bases": bases,
        "sectores": [{"c": i + 1, "n": nombres[i], "s12": next(g for g, (_, cs) in enumerate(M.GRUPOS_12) if i + 1 in cs)} for i in range(M.N)],
        "s12": [n for n, _ in M.GRUPOS_12],
        "serie": serie, "serie12": s12, "focos": {k: v for k, v in focos.items() if not k.startswith("_")}, "detalle": focos.get("_detalle"), "quiebre_base": quiebre, "sim": sim,
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"MIP: {len(anios)} años ({anios[0]}-{anios[-1]}), guardado en {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")
    if quiebre:
        print("Quiebre de base en 2013:", {k: (round(v, 3) if isinstance(v, float) else [round(x, 3) for x in v] if isinstance(v, list) else v) for k, v in quiebre.items()})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
