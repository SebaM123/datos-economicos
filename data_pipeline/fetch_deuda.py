"""Deuda pública de Chile (Banco Central, cuentas del sector público): deuda bruta y neta del Gobierno Central, del sector público consolidado, de las empresas públicas y
del Banco Central, en % del PIB y en pesos, trimestral desde 2006; y la deuda bruta del gobierno de otros países, para comparar.

Se guarda en docs/monitor/data/deuda.json, que lee la pestaña «Deuda pública» del Monitor. Códigos (familia F051 del Banco Central, trimestral):
  D7 = deuda bruta Gobierno Central, D9 = deuda neta Gobierno Central, F2 (M) = deuda bruta sector público consolidado, F3 = deuda neta sector público consolidado,
  D22 = empresas públicas, E7 = Banco Central, F2.STO.C = stock del Gobierno Central en millones de pesos. Comparación internacional: F019.DBPIB.PPIB.<país>.A (anual).
La deuda bruta es lo que se debe; la neta resta los activos financieros del Estado (por ejemplo, los fondos soberanos). El Banco Central publica el trimestre con
rezago: la Dipres suele adelantar una cifra provisoria (por ejemplo a septiembre) antes de que aparezca acá.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from credenciales import obtener_cliente

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "monitor" / "data" / "deuda.json"
HISTORICO = RAIZ / "data" / "historico.csv"
SERIES = {
    "bruta_gc": "F051.D7.PPB.C.Z.Z.T", "neta_gc": "F051.D9.PPB.C.Z.Z.T", "bruta_spc": "F051.F2.PPB.M.Z.Z.T", "neta_spc": "F051.F3.PPB.M.Z.Z.T",
    "bruta_emp": "F051.D22.PPB.C.Z.Z.T", "bruta_bc": "F051.E7.PPB.H.Z.Z.T", "stock_gc": "F051.F2.STO.C.Z.CLP.T",
}


def main() -> None:
    c = obtener_cliente()
    hasta = date.today().isoformat()
    t = c.cuadro(series=list(SERIES.values()), nombres=list(SERIES), desde="2006-01-01", hasta=hasta)
    t = t[t["bruta_gc"].notna()]
    if t.empty:
        raise RuntimeError("El Banco Central no devolvió la deuda del Gobierno Central")
    fin_trim = [(f + pd.offsets.QuarterEnd(0)) for f in t.index]  # la fecha del Banco Central es el inicio del trimestre

    h = pd.read_csv(HISTORICO, parse_dates=["fecha"])
    dolar = h[h["serie"] == "dolar_observado"].set_index("fecha")["valor"].sort_index()
    usd = []
    for f, stock in zip(fin_trim, t["stock_gc"]):
        s = dolar[dolar.index <= f]
        usd.append(round(float(stock) / float(s.iloc[-1])) if pd.notna(stock) and len(s) and f - s.index[-1] < pd.Timedelta(days=10) else None)

    r = c.buscar("Deuda bruta del Gobierno porcentaje del PIB")
    r = r[r["seriesId"].str.startswith("F019.DBPIB.PPIB")]
    paises = []
    for _, x in r.iterrows():
        nombre = x["spanishTitle"].split(",")[1].strip()
        s = c.cuadro(series=[x["seriesId"]], nombres=["v"], desde="1990-01-01", hasta=hasta)["v"].dropna()
        if len(s):
            paises.append({"nombre": nombre, "chile": nombre == "Chile", "anio": int(s.index[-1].year), "v": round(float(s.iloc[-1]), 1)})

    def col(nombre, dec=2):
        return [None if pd.isna(v) else round(float(v), dec) for v in t[nombre]]

    salida = {
        "descargado": date.today().isoformat(), "fuente": "Banco Central de Chile (cuentas del sector público; comparación internacional del Banco Central)",
        "fechas": [f.strftime("%Y-%m-%d") for f in fin_trim],
        **{k: col(k) for k in SERIES if k != "stock_gc"}, "stock_gc": col("stock_gc", 0), "usd_gc": usd,
        "paises": sorted(paises, key=lambda p: -p["v"]),
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Deuda pública: {len(t)} trimestres ({salida['fechas'][0]} a {salida['fechas'][-1]}), {len(paises)} países, guardado en {SALIDA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Deuda pública: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
