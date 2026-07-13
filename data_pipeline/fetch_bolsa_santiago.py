"""Trae el valor REAL del índice IPSA (no un proxy) desde la API pública
de la Bolsa de Santiago. Solo entrega una ventana reciente (~1 mes), no
historia profunda — para eso se usa el índice de Yahoo (2010-2019) más
lo que este script vaya acumulando día a día de acá en adelante.
"""

import requests

BASE_URL = "https://www.bolsadesantiago.com"


def obtener_sesion() -> tuple[requests.Session, str]:
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": "Mozilla/5.0"})
    respuesta = sesion.get(f"{BASE_URL}/api/Securities/csrfToken", timeout=15)
    respuesta.raise_for_status()
    token = respuesta.json()["csrf"]
    return sesion, token


def obtener_ipsa_real_reciente() -> list[dict]:
    sesion, token = obtener_sesion()
    respuesta = sesion.post(
        f"{BASE_URL}/api/RV_Indices/getIndiceHistoryDescarga",
        json={"symbol": "SP IPSA", "condividendo": "S"},
        headers={"X-CSRF-Token": token, "Content-Type": "application/json"},
        timeout=15,
    )
    respuesta.raise_for_status()
    datos = respuesta.json().get("listaResult", [])

    filas = []
    for punto in datos:
        fecha = punto["FECHA"].split(" ")[0]
        filas.append({"fecha": fecha, "serie": "ipsa_indice_real", "valor": float(punto["CLOSE"])})
    return filas


if __name__ == "__main__":
    from common import append_historico

    filas = obtener_ipsa_real_reciente()
    print(f"{len(filas)} observaciones reales del IPSA obtenidas")
    agregadas = append_historico(filas)
    print(f"Filas nuevas agregadas a historico.csv: {agregadas}")
