from pathlib import Path

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"

NOMBRES_SERIES = {
    "tpm": "TPM (%)",
    "ipc_variacion_mensual": "IPC - variación mensual (%)",
    "desempleo": "Tasa de desempleo (%)",
    "imacec": "IMACEC",
    "ipsa": "IPSA (vía ETF, no el índice puro)",
    "tipo_cambio": "Tipo de cambio (USD/CLP)",
}
