"""Trae el último dato disponible de IPSA y tipo de cambio (USD/CLP) vía Yahoo Finance."""

from datetime import date

import yfinance as yf

from common import append_historico

TICKERS = {
    # ^IPSA (el índice puro) no tiene historia en Yahoo Finance entre 2019 y hoy,
    # solo la cotización del momento. Usamos el ETF que lo replica, que sí tiene
    # serie diaria continua desde 2013. El nivel no coincide con el índice oficial,
    # pero la trayectoria/variación porcentual sí es representativa.
    "ipsa": "CFMITNIPSA.SN",
    "tipo_cambio": "USDCLP=X",
}


def obtener_snapshot() -> list[dict]:
    hoy = date.today().isoformat()
    filas = []
    for serie, ticker in TICKERS.items():
        historial = yf.Ticker(ticker).history(period="5d")
        if historial.empty:
            continue
        ultimo_valor = float(historial["Close"].iloc[-1])
        filas.append({"fecha": hoy, "serie": serie, "valor": ultimo_valor})
    return filas


def obtener_historico(desde: str) -> list[dict]:
    filas = []
    for serie, ticker in TICKERS.items():
        historial = yf.Ticker(ticker).history(start=desde)
        for fecha, fila in historial.iterrows():
            filas.append({"fecha": fecha.date().isoformat(), "serie": serie, "valor": float(fila["Close"])})
    return filas


def main() -> None:
    filas = obtener_snapshot()
    if not filas:
        print("No se obtuvieron datos de mercado.")
        return
    agregadas = append_historico(filas)
    for fila in filas:
        print(f"{fila['serie']}: {fila['valor']}")
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")


if __name__ == "__main__":
    main()
