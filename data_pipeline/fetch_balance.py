"""Balance fiscal del Gobierno Central de Chile (Banco Central, cuentas del sector público): ingresos, gastos y balance efectivo mensual (base devengada)
y balance estructural anual, para la pestaña «Déficit fiscal» del Monitor (docs/monitor/data/balance.json).

Códigos (familia F051 del Banco Central; montos en millones de pesos):
  BT02 = ingresos totales, BT03 = gasto total (incluye la inversión: es el gasto que informa la Dipres), BT04 = préstamo neto / endeudamiento neto
  (el balance efectivo, = ingresos - gasto; negativo = déficit), todos «Gobierno central total, devengado», mensual;
  G11 (PPB, anual) = balance cíclicamente ajustado o estructural, en % del PIB.
El PIB nominal anual sale de data/composicion.csv. El balance efectivo de 2025 coincide con el que informó la Dipres (-$9.525.510 millones, 2,8% del PIB).
El balance estructural lo calcula la Dipres con un comité de expertos y se revisa: la cifra del Banco Central puede diferir de la primera estimación que dio a conocer la Dipres.
"""

import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

from credenciales import obtener_cliente

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "docs" / "monitor" / "data" / "balance.json"
COMPOSICION = RAIZ / "data" / "composicion.csv"
SERIES = {"ingresos": "F051.BT02.FLU.C.D.CLP.M", "gasto_total": "F051.BT03.FLU.C.D.CLP.M", "balance": "F051.BT04.FLU.C.D.CLP.M"}


def main() -> None:
    c = obtener_cliente()
    hasta = date.today().isoformat()
    t = c.cuadro(series=list(SERIES.values()), nombres=list(SERIES), desde="2001-01-01", hasta=hasta).dropna()
    if t.empty:
        raise RuntimeError("El Banco Central no devolvió el balance del Gobierno Central")
    if ((t["ingresos"] - t["gasto_total"] - t["balance"]).abs() > 20000).any():  # hasta 0,03 billones de diferencia por redondeo en cifras antiguas
        raise RuntimeError("Ingresos - gasto total no coincide con el balance")
    est = c.cuadro(series=["F051.G11.PPB.C.Z.CLP.A"], nombres=["v"], desde="2001-01-01", hasta=hasta)["v"].dropna()
    g = pd.read_csv(COMPOSICION, parse_dates=["fecha"])
    g = g[g["serie"] == "g_pib"].set_index("fecha")["valor"]
    pib = {int(a): round(float(v.sum()) * 1000) for a, v in g.groupby(g.index.year) if len(v) == 4}  # millones de pesos
    salida = {
        "descargado": date.today().isoformat(), "fuente": "Banco Central de Chile (cuentas del sector público, base devengada)", "unidad": "millones de pesos nominales",
        "meses": [f.strftime("%Y-%m-%d") for f in t.index],
        **{k: [round(float(v)) for v in t[k]] for k in ("ingresos", "gasto_total", "balance")},
        "estructural": {str(f.year): round(float(v), 2) for f, v in est.items()}, "pib": {str(a): v for a, v in pib.items()},
    }
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Balance fiscal: {len(t)} meses ({salida['meses'][0]} a {salida['meses'][-1]}), estructural {est.index[0].year}-{est.index[-1].year}, guardado en {SALIDA}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # no debe tumbar el resto del pipeline: la pestaña sigue con el archivo anterior
        print(f"Balance fiscal: no se pudo actualizar ({type(error).__name__}: {error})")
        sys.exit(1)
