"""Presupuesto del Gobierno Central de Chile (Dipres, vía datos.gob.cl): ejecución presupuestaria y Ley de Presupuestos por ministerio (partida).

Fuente: los conjuntos «Ejecución Presupuestaria a <mes> de <año> del Gobierno Central» y «Ley de Presupuestos Inicial y Vigente a <mes> de <año>…» que la Dirección
de Presupuestos publica en https://datos.gob.cl (API CKAN pública, sin clave). Cada uno trae CSV a nivel nacional y por partida (cada ministerio u organismo es una
«partida»), con los montos por subtítulo (tipo de ingreso o gasto) en miles de pesos nominales. Hay cierres de diciembre desde 2009 y meses del año en curso.

Se guarda un resumen en docs/monitor/data/presupuesto.json, que lee la pestaña «Presupuesto fiscal» del Monitor:
  - cierres anuales (diciembre) por partida y subtítulo, y totales nacionales consolidados, en millones de pesos;
  - el año en curso: Ley inicial, Ley vigente y ejecución acumulada al último mes publicado, y la ejecución al mismo mes del año anterior;
  - el PIB nominal anual (de data/composicion.csv) para expresar todo como % del PIB.

OJO con dos cosas al leer los números:
  - La suma de las partidas NO es el gasto del Gobierno Central: el Tesoro Público (partida 50) transfiere casi todo su presupuesto a los ministerios como «aporte fiscal
    libre» (subtítulo 27, que cada ministerio recibe como ingreso, subtítulo 09), así que contarlo dos veces duplica el gasto. La pestaña descuenta ese aporte.
  - Los cierres anuales ya publicados no cambian, así que solo se bajan los años que faltan; el año en curso se vuelve a bajar en cada corrida (`--forzar` rehace todo).
"""

import argparse
import io
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd
import requests

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "monitor" / "data" / "presupuesto.json"
COMPOSICION = RAIZ / "data" / "composicion.csv"
CKAN = "https://datos.gob.cl/api/3/action/package_search"
ANIO_DESDE = 2009
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
SUBTITULOS_GASTO = [21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34]
SUBTITULOS_INGRESO = [1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
CONECTORES = {"de", "del", "la", "las", "los", "el", "y", "e", "en", "para", "a", "al"}
CABECERA = {"User-Agent": "Mozilla/5.0 (Monitor Chile; datos abiertos)"}


def _get(url: str, params: dict | None = None, intentos: int = 4) -> requests.Response:
    for n in range(1, intentos + 1):
        try:
            r = requests.get(url, params=params, headers=CABECERA, timeout=90)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as error:
            if n == intentos:
                raise
            print(f"  reintento {n}/{intentos - 1} tras error: {error}")
            time.sleep(5)
    raise RuntimeError("inalcanzable")


def catalogo() -> list[dict]:
    """Todos los conjuntos de la Dipres en datos.gob.cl: [{title, resources: {nombre: url}}]."""
    salida, inicio = [], 0
    while True:
        r = _get(CKAN, {"fq": "organization:direccion_de_presupuestos", "rows": 500, "start": inicio}).json()["result"]
        salida += [{"title": re.sub(r"\s+", " ", p["title"]).strip(), "resources": {x["name"].strip(): x["url"] for x in p["resources"]}} for p in r["results"]]
        inicio += 500
        if inicio >= r["count"]:
            return salida


def _leer(url: str) -> pd.DataFrame:
    raw = _get(url).content
    for enc in ("utf-8-sig", "latin-1"):
        try:
            df = pd.read_csv(io.StringIO(raw.decode(enc)), sep=";", dtype=str)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [re.sub(r"\s+", " ", c).strip().lower() for c in df.columns]
    df = df[df["moneda"].str.upper().str.startswith("PESO")].copy()
    df.insert(0, "sub", pd.to_numeric(df["subtítulo"], errors="coerce"))  # al inicio, para que la última columna siga siendo el monto
    return df.dropna(subset=["sub"])


def _num(serie: pd.Series) -> pd.Series:
    """'5.231.358.682' (miles de pesos, con punto de miles) -> millones de pesos."""
    return pd.to_numeric(serie.str.replace(".", "", regex=False).str.replace(",", ".", regex=False), errors="coerce").fillna(0) / 1000


def _propio(nombre: str) -> str:
    p = str(nombre).strip().lower().split()
    return " ".join(w if (i and w in CONECTORES) else w.capitalize() for i, w in enumerate(p))


def _buscar(cat: list[dict], regex: str) -> dict | None:
    for p in cat:
        if re.match(regex, p["title"], re.I):
            return p
    return None


def _ejecucion(cat, anio: int, mes: int) -> dict | None:
    m = MESES[mes - 1]
    return _buscar(cat, rf"^ejecución presupuestaria (a|al) {m} de {anio} del gobierno central( - (ejecución )?total)?$")


def _ley(cat, anio: int, mes: int) -> dict | None:
    m = MESES[mes - 1]
    return _buscar(cat, rf"^ley de presupuestos inicial y vigente (a|al) {m} de {anio} del gobierno central( - total)?$")


def _recursos_cierre(cat, anio: int, tipo: str) -> dict | None:
    """Recursos {'A nivel Nacional': url, 'A nivel Partida': url} del cierre de diciembre. Hasta 2016 vienen en un solo conjunto histórico, un archivo por año."""
    if anio <= 2016:
        clave = "ejecución presupuestaria" if tipo == "ejecucion" else "ley de presupuestos inicial y vigente"
        p = _buscar(cat, rf"^histórico {clave} de 2009 a 2016 del gobierno central$")
        return {n: p["resources"][f"{n} {anio}"] for n in ("A nivel Nacional", "A nivel Partida") if p and f"{n} {anio}" in p["resources"]} or None
    p = (_ejecucion if tipo == "ejecucion" else _ley)(cat, anio, 12)
    return p["resources"] if p else None


def _cierre(cat, anio: int) -> dict | None:
    """Ejecución de un cierre anual: gasto por partida y subtítulo y totales nacionales (millones de pesos)."""
    rec = _recursos_cierre(cat, anio, "ejecucion")
    if not rec or "A nivel Partida" not in rec or "A nivel Nacional" not in rec:
        return None
    par, nac = _leer(rec["A nivel Partida"]), _leer(rec["A nivel Nacional"])
    par["v"], nac["v"] = _num(par.iloc[:, -1]), _num(nac.iloc[:, -1])  # la última columna es la ejecución acumulada al mes
    return {
        "nacional": {int(s): float(v) for s, v in nac.groupby("sub")["v"].sum().items()},
        "partidas": {str(c).zfill(2): {"n": _propio(g["nombre partida"].iloc[0]), "v": {int(s): float(v) for s, v in g.groupby("sub")["v"].sum().items()}}
                     for c, g in par.groupby("partida")},
    }


def _estado_ytd(cat, anio: int, mes: int) -> dict | None:
    """Ley inicial, Ley vigente y ejecución acumulada de un mes, por partida y subtítulo (millones de pesos)."""
    pe, pl = _ejecucion(cat, anio, mes), _ley(cat, anio, mes)
    if not pe:
        return None
    ej = _leer(pe["resources"]["A nivel Partida"])
    ej["v"] = _num(ej.iloc[:, -1])
    salida = {"ej": {}, "li": {}, "lv": {}}
    for c, g in ej.groupby("partida"):
        salida["ej"][str(c).zfill(2)] = {int(s): float(v) for s, v in g.groupby("sub")["v"].sum().items()}
        salida.setdefault("nombres", {})[str(c).zfill(2)] = _propio(g["nombre partida"].iloc[0])
    nac = _leer(pe["resources"]["A nivel Nacional"])
    nac["v"] = _num(nac.iloc[:, -1])
    salida["ej_nac"] = {int(s): float(v) for s, v in nac.groupby("sub")["v"].sum().items()}
    if pl:
        ley = _leer(pl["resources"]["A nivel Partida"])
        col_i = next(c for c in ley.columns if c.startswith("monto ley inicial"))
        col_v = next(c for c in ley.columns if c.startswith("monto ley vigente"))
        for clave, col in (("li", col_i), ("lv", col_v)):
            ley["v"] = _num(ley[col])
            for c, g in ley.groupby("partida"):
                salida[clave][str(c).zfill(2)] = {int(s): float(v) for s, v in g.groupby("sub")["v"].sum().items()}
        ln = _leer(pl["resources"]["A nivel Nacional"])
        for clave, col in (("li", col_i), ("lv", col_v)):
            ln["v"] = _num(ln[col])
            salida[f"{clave}_nac"] = {int(s): float(v) for s, v in ln.groupby("sub")["v"].sum().items()}
    return salida


def _pib() -> tuple[dict[int, float], dict]:
    """PIB nominal anual (millones de pesos) = suma de los cuatro trimestres de data/composicion.csv (miles de millones de pesos), y el último año móvil."""
    c = pd.read_csv(COMPOSICION, parse_dates=["fecha"])
    g = c[c["serie"] == "g_pib"].sort_values("fecha").set_index("fecha")["valor"]
    anual = {int(a): float(v.sum()) * 1000 for a, v in g.groupby(g.index.year) if len(v) == 4}
    movil = g.rolling(4).sum().dropna()
    return anual, {"fecha": movil.index[-1].strftime("%Y-%m-%d"), "valor": float(movil.iloc[-1]) * 1000}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true", help="bajar de nuevo todos los años")
    args = parser.parse_args()

    previo = {}
    if SALIDA.exists() and not args.forzar:
        previo = json.loads(SALIDA.read_text(encoding="utf-8"))
    cat = catalogo()
    print(f"Catálogo Dipres: {len(cat)} conjuntos")

    cierres: dict[int, dict] = {}
    for a in previo.get("anios", []):
        cierres[a] = {"nacional": {int(k): v for k, v in previo["nacional"][str(a)].items()},
                      "partidas": {c: {"n": p["nombres"].get(str(a), p["n"]), "v": {int(s): v for s, v in p["gasto"].get(str(a), {}).items()}} for c, p in previo["partidas"].items() if str(a) in p["gasto"]}}
    for a in range(ANIO_DESDE, date.today().year):
        if a in cierres:
            continue
        c = _cierre(cat, a)
        if c:
            cierres[a] = c
            print(f"  cierre {a}: {len(c['partidas'])} partidas")
        else:
            print(f"  cierre {a}: no disponible todavía")
    if not cierres:
        raise RuntimeError("No se pudo leer ningún cierre anual de la Dipres")
    anios = sorted(cierres)

    # año en curso: último mes publicado (con su Ley y el mismo mes del año anterior)
    ytd = None
    anio_ytd = anios[-1] + 1  # el año siguiente al último cierre publicado
    if anio_ytd <= date.today().year:
        for mes in range(12, 0, -1):
            actual = _estado_ytd(cat, anio_ytd, mes)
            if actual:
                previo_ytd = _estado_ytd(cat, anio_ytd - 1, mes)
                ytd = {"anio": anio_ytd, "mes": mes, "mes_nombre": MESES[mes - 1].capitalize(), "actual": actual, "previo": {"ej": previo_ytd["ej"], "ej_nac": previo_ytd["ej_nac"]} if previo_ytd else None}
                print(f"  año en curso: {MESES[mes - 1]} de {anio_ytd}")
                break

    # partidas: nombre vigente y nombres anteriores
    codigos = sorted({c for a in anios for c in cierres[a]["partidas"]} | (set(ytd["actual"]["ej"]) if ytd else set()))
    partidas = {}
    for c in codigos:
        nombres = {str(a): cierres[a]["partidas"][c]["n"] for a in anios if c in cierres[a]["partidas"]}
        if ytd and c in ytd["actual"]["nombres"]:
            nombres[str(ytd["anio"])] = ytd["actual"]["nombres"][c]
        partidas[c] = {
            "n": nombres[max(nombres)], "nombres": nombres,
            "gasto": {str(a): {str(s): round(v, 1) for s, v in cierres[a]["partidas"][c]["v"].items() if s in SUBTITULOS_GASTO} for a in anios if c in cierres[a]["partidas"]},
        }
    pib_anual, pib_movil = _pib()
    salida = {
        "descargado": date.today().isoformat(), "fuente": "Dirección de Presupuestos (Dipres), Ejecución Presupuestaria y Ley de Presupuestos, Gobierno Central", "unidad": "millones de pesos nominales",
        "anios": anios,
        "nacional": {str(a): {str(s): round(v, 1) for s, v in cierres[a]["nacional"].items()} for a in anios},
        "partidas": partidas,
        "pib": {str(a): round(pib_anual[a]) for a in anios if a in pib_anual}, "pib_movil": pib_movil,
    }
    if ytd:
        def comp(d):  # {partida: {sub: v}} -> redondeado y solo gastos
            return {c: {str(s): round(v, 1) for s, v in sub.items() if s in SUBTITULOS_GASTO} for c, sub in d.items()}
        a = ytd["actual"]
        salida["ytd"] = {
            "anio": ytd["anio"], "mes": ytd["mes"], "mes_nombre": ytd["mes_nombre"],
            "ejecucion": comp(a["ej"]), "ley_inicial": comp(a["li"]), "ley_vigente": comp(a["lv"]),
            "previo": comp(ytd["previo"]["ej"]) if ytd["previo"] else None,
            "nacional": {k: {str(s): round(v, 1) for s, v in a[f"{k}_nac"].items()} for k in ("ej", "li", "lv") if f"{k}_nac" in a},
            "nacional_previo": {str(s): round(v, 1) for s, v in ytd["previo"]["ej_nac"].items()} if ytd["previo"] else None,
        }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Presupuesto: {len(anios)} cierres ({anios[0]}-{anios[-1]}), {len(partidas)} partidas, guardado en {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Presupuesto: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
