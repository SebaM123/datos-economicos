from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"
REVISIONES_PATH = Path(__file__).resolve().parent.parent / "data" / "revisiones.csv"

COLUMNS = ["fecha", "serie", "valor"]
COLUMNAS_REVISIONES = ["serie", "fecha", "valor_anterior", "valor_nuevo", "detectado_el"]


def _registrar_revisiones(existentes: pd.DataFrame, nuevas: pd.DataFrame, ruta: Path) -> int:
    """Archiva los valores que van a ser REEMPLAZADOS: filas (fecha, serie) que ya
    estaban guardadas y que la fuente ahora entrega con otro valor (típico del
    Banco Central: revisa el IMACEC/PIB de meses anteriores cada vez que
    publica). El valor vigente en historico.csv pasa a ser el revisado (el
    correcto hoy), pero el anterior no se pierde: queda en revisiones.csv con la
    fecha en que se detectó el cambio.
    """
    nuevas = nuevas.drop_duplicates(subset=["fecha", "serie"], keep="last")
    cruce = existentes.merge(nuevas, on=["fecha", "serie"], suffixes=("_anterior", "_nuevo"))
    cambiaron = ~np.isclose(
        cruce["valor_anterior"].astype(float), cruce["valor_nuevo"].astype(float),
        rtol=1e-9, atol=1e-12, equal_nan=True,
    )
    cruce = cruce[cambiaron]
    if cruce.empty:
        return 0

    hoy = datetime.now(ZoneInfo("America/Santiago")).date().isoformat()
    registro = cruce.assign(detectado_el=hoy)[COLUMNAS_REVISIONES]
    if ruta.exists():
        registro = pd.concat([pd.read_csv(ruta, dtype={"fecha": str, "detectado_el": str}), registro], ignore_index=True)
    registro = registro.drop_duplicates(subset=["serie", "fecha", "valor_anterior", "valor_nuevo"], keep="first")
    registro.sort_values(["detectado_el", "serie", "fecha"], ascending=[False, True, True]).to_csv(ruta, index=False)
    return len(cruce)


def append_historico(rows: list[dict], csv_path: Path = HISTORICO_PATH, registrar_revisiones: bool = False) -> int:
    """Agrega filas nuevas a historico.csv, sin duplicar (fecha, serie) ya existentes.

    Devuelve la cantidad de filas efectivamente agregadas.

    `registrar_revisiones=True` (series oficiales que se revisan: Banco Central,
    FRED, Banco Mundial): si una fila ya guardada llega con otro valor, el valor
    nuevo reemplaza al viejo en historico.csv pero el viejo se archiva en
    revisiones.csv. Se deja en False para datos de mercado, donde el valor de
    una misma fecha cambia a lo largo del día (cotización intradía), que no es
    una revisión.
    """
    nuevas = pd.DataFrame(rows, columns=COLUMNS)
    nuevas["fecha"] = pd.to_datetime(nuevas["fecha"]).dt.strftime("%Y-%m-%d")

    ya_existia = csv_path.exists()
    filas_previas = 0

    if ya_existia:
        existentes = pd.read_csv(csv_path, dtype={"fecha": str})
        filas_previas = len(existentes)
        if registrar_revisiones:
            n_rev = _registrar_revisiones(existentes, nuevas, csv_path.parent / REVISIONES_PATH.name)
            if n_rev:
                print(f"  Revisiones detectadas (valor anterior archivado en revisiones.csv): {n_rev}")
        combinado = pd.concat([existentes, nuevas], ignore_index=True)
    else:
        combinado = nuevas

    combinado = combinado.drop_duplicates(subset=["fecha", "serie"], keep="last")
    combinado = combinado.sort_values(["serie", "fecha"])

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    combinado.to_csv(csv_path, index=False)

    return len(combinado) - filas_previas
