from pathlib import Path

import pandas as pd

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"

COLUMNS = ["fecha", "serie", "valor"]


def append_historico(rows: list[dict], csv_path: Path = HISTORICO_PATH) -> int:
    """Agrega filas nuevas a historico.csv, sin duplicar (fecha, serie) ya existentes.

    Devuelve la cantidad de filas efectivamente agregadas.
    """
    nuevas = pd.DataFrame(rows, columns=COLUMNS)
    nuevas["fecha"] = pd.to_datetime(nuevas["fecha"]).dt.strftime("%Y-%m-%d")

    ya_existia = csv_path.exists()
    filas_previas = 0

    if ya_existia:
        existentes = pd.read_csv(csv_path, dtype={"fecha": str})
        filas_previas = len(existentes)
        combinado = pd.concat([existentes, nuevas], ignore_index=True)
    else:
        combinado = nuevas

    combinado = combinado.drop_duplicates(subset=["fecha", "serie"], keep="last")
    combinado = combinado.sort_values(["serie", "fecha"])

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    combinado.to_csv(csv_path, index=False)

    return len(combinado) - filas_previas
