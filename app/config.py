from pathlib import Path

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"

NOMBRES_SERIES = {
    "tpm": "TPM (%)",
    "ipc_variacion_mensual": "IPC - variación mensual (%)",
    "desempleo": "Tasa de desempleo (%)",
    "imacec": "IMACEC",
    "ipsa_indice_real": "IPSA - índice real (sin datos 2019-2026)",
    "ipsa_etf": "IPSA - vía ETF (tendencia continua, no el índice puro)",
    "tipo_cambio": "Tipo de cambio (USD/CLP)",
    "eof_tpm_proxima_reunion": "Expectativa TPM próxima reunión (EOF, %)",
    "eof_inflacion_12m": "Expectativa inflación 12 meses (EOF, %)",
    "eof_tipo_cambio_7d": "Expectativa tipo de cambio 7 días (EOF)",
}
