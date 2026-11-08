"""Fondos de pensiones de Chile: patrimonio por tipo de fondo (A-E) y por AFP desde 2002, en relación al PIB, y comparación con otros países.

Fuentes (todas públicas, sin clave salvo el Banco Central):
  - Superintendencia de Pensiones: valor diario del patrimonio de cada fondo y AFP (https://www.spensiones.cl/apps/valoresCuotaFondo/), exportación CSV por rango de años.
    Se guarda el último día con datos completos de cada mes.
  - Banco Central: «Activos de los fondos de pensiones, porcentaje del PIB» (F029.ACF.PPIB18.AFP.T, trimestral), la cifra oficial para contrastar.
  - OCDE: «Assets earmarked for retirement» (OECD.DAF.CM, DF_PA) en % del PIB por país, para comparar a Chile con el resto.
  - PIB nominal de los últimos 4 trimestres: data/composicion.csv; dólar observado: data/historico.csv (desde 2010).

Qué mide cada cosa
  - La serie diaria de la Superintendencia es el PATRIMONIO de los fondos, que es ~1,4% menor que el «valor de los fondos» (activos) que citan sus reportes mensuales,
    porque descuenta obligaciones pendientes. La relación con el PIB aquí se calcula con el patrimonio, así que sale ~1 punto bajo la oficial (activos); la cifra oficial
    trimestral del Banco Central se muestra aparte.
  - Para cada mes se divide por el PIB de los últimos 4 trimestres cerrados al fin de ese mes (si el trimestre aún no se publica, se usa el último disponible).
  - Los datos de la Superintendencia se actualizan a diario; solo se vuelven a bajar los últimos 2 años (los anteriores se conservan del archivo previo; `--forzar` baja todo).
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
SALIDA = RAIZ / "docs" / "monitor" / "data" / "pensiones.json"
ENTIDADES = RAIZ / "docs" / "monitor" / "data" / "comparador" / "entidades.json"
COMPOSICION = RAIZ / "data" / "composicion.csv"
HISTORICO = RAIZ / "data" / "historico.csv"
URL_SP = "https://www.spensiones.cl/apps/valoresCuotaFondo/vcfAFPxls.php"
URL_OCDE = "https://sdmx.oecd.org/public/rest/data/OECD.DAF.CM,DSD_FP@DF_PA,1.0/all"
TIPOS = ["A", "B", "C", "D", "E"]
CABECERA = {"User-Agent": "Mozilla/5.0 (Monitor Chile; datos abiertos)"}
OCDE = {"AUS", "AUT", "BEL", "CAN", "CHL", "COL", "CRI", "CZE", "DNK", "EST", "FIN", "FRA", "DEU", "GRC", "HUN", "ISL", "IRL", "ISR", "ITA", "JPN", "KOR", "LVA", "LTU", "LUX",
        "MEX", "NLD", "NZL", "NOR", "POL", "PRT", "SVK", "SVN", "ESP", "SWE", "CHE", "TUR", "GBR", "USA"}


def _get(url: str, params: dict | None = None, headers: dict | None = None, intentos: int = 4, timeout: int = 150) -> requests.Response:
    for n in range(1, intentos + 1):
        try:
            r = requests.get(url, params=params, headers={**CABECERA, **(headers or {})}, timeout=timeout)
            r.raise_for_status()
            return r
        except requests.exceptions.RequestException as error:
            if n == intentos:
                raise
            print(f"  reintento {n}/{intentos - 1} tras error: {error}")
            time.sleep(6)
    raise RuntimeError("inalcanzable")


def _fecha_confirmada() -> str:
    """Último día con valores confirmados, que la propia página de la Superintendencia usa para pedir la exportación (fecconf=AAAAMMDD)."""
    m = re.search(r"fecconf=(\d{8})", _get("https://www.spensiones.cl/apps/valoresCuotaFondo/vcfAFP.php", {"tf": "A"}).text)
    return m.group(1) if m else date.today().strftime("%Y%m%d")


def _patrimonio_diario(tipo: str, desde: int, hasta: int, confirmada: str) -> dict[str, dict[str, int | None]]:
    """{fecha: {AFP: patrimonio en pesos o None}} para un tipo de fondo. El CSV repite la cabecera cada vez que cambia el conjunto de AFP."""
    r = _get(URL_SP, {"aaaaini": desde, "aaaafin": hasta, "tf": tipo, "fecconf": confirmada})
    salida, afps = {}, None
    for linea in r.content.decode("latin-1").splitlines():
        if linea.startswith("Valores Provisorios"):  # los últimos días vienen aparte, sujetos a confirmación: no se publican
            break
        if linea.startswith("Fecha"):
            afps = [a.strip() for a in linea.split(";")[1:] if a.strip()]
            continue
        m = re.match(r"(\d{4}-\d{2}-\d{2});(.*)", linea)
        if m and afps:
            c = m.group(2).split(";")  # por AFP: valor cuota, valor patrimonio
            salida[m.group(1)] = {a: (int(c[2 * i + 1]) if 2 * i + 1 < len(c) and c[2 * i + 1].strip().isdigit() else None) for i, a in enumerate(afps)}
    return salida


def _fin_de_mes(diarios: dict[str, dict[str, dict]]) -> dict[str, dict]:
    """Para cada mes, el último día con todos los tipos y todas las AFP informados: {fecha: {tipo: {afp: pesos}}}."""
    fechas = sorted(set.intersection(*(set(d) for d in diarios.values())))
    completas = [f for f in fechas if all(v is not None for t in diarios.values() for v in t[f].values())]
    ultimo_por_mes = {}
    for f in completas:
        ultimo_por_mes[f[:7]] = f
    return {f: {t: diarios[t][f] for t in diarios} for f in ultimo_por_mes.values()}


def _pib_4q() -> pd.Series:
    c = pd.read_csv(COMPOSICION, parse_dates=["fecha"])
    g = c[c["serie"] == "g_pib"].sort_values("fecha").set_index("fecha")["valor"]
    cierre = g.index + pd.offsets.QuarterEnd(0)  # fin del trimestre
    return pd.Series(g.rolling(4).sum().values * 1000, index=cierre).dropna()  # millones de pesos


def _bcch() -> list[list]:
    """Serie oficial del Banco Central: activos de los fondos de pensiones como % del PIB, trimestral."""
    import os
    if not (os.environ.get("BCCH_USER") and os.environ.get("BCCH_PASSWORD")):
        from dotenv import load_dotenv
        load_dotenv(RAIZ / ".env")
    from credenciales import obtener_cliente
    t = obtener_cliente().cuadro(series=["F029.ACF.PPIB18.AFP.T"], nombres=["v"], desde="2003-01-01", hasta=date.today().isoformat())["v"].dropna()
    # fecha = fin del trimestre
    return [[(f + pd.offsets.QuarterEnd(0)).strftime("%Y-%m-%d"), round(float(v), 2)] for f, v in t.items()]


def _ocde() -> dict:
    r = _get(URL_OCDE, {"startPeriod": 2015, "dimensionAtObservation": "AllDimensions"}, {"Accept": "application/vnd.sdmx.data+csv; charset=utf-8"}, timeout=180)
    d = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
    d = d[(d["UNIT_MEASURE"] == "PT_B1GQ") & d["VEHICLE_TYPE"].isin(["_T", "PF"])]
    nombres = {e["id"]: e["nombre"] for e in json.loads(ENTIDADES.read_text(encoding="utf-8")) if e["tipo"] == "pais"} if ENTIDADES.exists() else {}
    paises = []
    for pais, g in d.groupby("REF_AREA"):
        fila = {"id": pais, "nombre": nombres.get(pais, pais), "ocde": pais in OCDE}
        for clave, veh in (("total", "_T"), ("pf", "PF")):
            x = g[g["VEHICLE_TYPE"] == veh].sort_values("TIME_PERIOD")
            if len(x):
                fila[clave], fila[f"{clave}_anio"] = round(float(x["OBS_VALUE"].iloc[-1]), 1), int(x["TIME_PERIOD"].iloc[-1])
        if "total" in fila or "pf" in fila:
            paises.append(fila)
    chile = d[(d["REF_AREA"] == "CHL") & (d["VEHICLE_TYPE"] == "_T")].sort_values("TIME_PERIOD")
    return {"paises": sorted(paises, key=lambda p: -(p.get("pf") or p.get("total") or 0)),
            "chile": [[int(a), round(float(v), 1)] for a, v in zip(chile["TIME_PERIOD"], chile["OBS_VALUE"])]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forzar", action="store_true", help="bajar todo el historial desde 2002")
    args = parser.parse_args()
    hoy = date.today()
    previo = json.loads(SALIDA.read_text(encoding="utf-8")) if SALIDA.exists() and not args.forzar else {}
    desde = (hoy.year - 1) if previo else 2002

    confirmada = _fecha_confirmada()
    diarios = {t: _patrimonio_diario(t, desde, hoy.year, confirmada) for t in TIPOS}
    nuevos = _fin_de_mes(diarios)
    print(f"  Superintendencia: {len(nuevos)} meses bajados desde {desde}")

    # meses: conservar los anteriores a `desde` del archivo previo y reemplazar el resto
    meses: dict[str, dict] = {}
    for i, f in enumerate(previo.get("fechas", [])):
        if int(f[:4]) < desde:
            meses[f] = {"tipos": {t: previo["tipos"][t][i] for t in TIPOS}, "afp": {a: v[i] for a, v in previo["afp"].items() if v[i] is not None}}
    for f, por_tipo in nuevos.items():
        afp: dict[str, float] = {}
        for t in TIPOS:
            for a, v in por_tipo[t].items():
                afp[a] = afp.get(a, 0) + v / 1e6
        meses[f] = {"tipos": {t: round(sum(por_tipo[t].values()) / 1e6) for t in TIPOS}, "afp": {a: round(v) for a, v in afp.items()}}
    fechas = sorted(meses)
    ult = fechas[-1]
    tabla = {}
    if ult in nuevos:
        for t in TIPOS:
            for a, v in nuevos[ult][t].items():
                tabla.setdefault(a, {})[t] = round(v / 1e6)
    else:
        tabla = previo.get("ultimo", {}).get("afp_tipo", {})

    total = [sum(meses[f]["tipos"].values()) for f in fechas]
    pib = _pib_4q()
    pib_f = [float(pib[pib.index <= pd.Timestamp(f)].iloc[-1]) if (pib.index <= pd.Timestamp(f)).any() else None for f in fechas]
    h = pd.read_csv(HISTORICO, parse_dates=["fecha"])
    dolar = h[h["serie"] == "dolar_observado"].set_index("fecha")["valor"].sort_index()
    usd = []
    for f, tot in zip(fechas, total):
        s = dolar[dolar.index <= pd.Timestamp(f)]
        usd.append(round(tot / float(s.iloc[-1])) if len(s) and pd.Timestamp(f) - s.index[-1] < pd.Timedelta(days=10) else None)

    salida = {
        "descargado": hoy.isoformat(), "fuente": "Superintendencia de Pensiones (patrimonio), Banco Central (% del PIB oficial) y OCDE", "unidad": "millones de pesos nominales",
        "fechas": fechas, "tipos": {t: [meses[f]["tipos"][t] for f in fechas] for t in TIPOS}, "total": total,
        "afp": {a: [meses[f]["afp"].get(a) for f in fechas] for a in sorted({a for f in fechas for a in meses[f]["afp"]})},
        "pib_4q": [round(v) if v else None for v in pib_f], "pct_pib": [round(t / p * 100, 2) if p else None for t, p in zip(total, pib_f)], "usd": usd,
        "ultimo": {"fecha": ult, "afp_tipo": tabla},
    }
    try:
        salida["bcch_pct_pib"] = _bcch()
    except Exception as error:  # sin credenciales o Banco Central en mantención: se conserva lo anterior
        print(f"  Banco Central: no se pudo leer ({type(error).__name__}); se conserva la serie anterior")
        salida["bcch_pct_pib"] = previo.get("bcch_pct_pib", [])
    try:
        salida["ocde"] = _ocde()
    except Exception as error:
        print(f"  OCDE: no se pudo leer ({type(error).__name__}); se conserva lo anterior")
        salida["ocde"] = previo.get("ocde")
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Pensiones: {len(fechas)} meses ({fechas[0]} a {fechas[-1]}), {len(salida['afp'])} AFP, guardado en {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Pensiones: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
