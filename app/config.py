from pathlib import Path

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"

NOMBRES_SERIES = {
    "tpm": "TPM (%)",
    "ipc_variacion_mensual": "IPC - variación mensual (%)",
    "desempleo": "Tasa de desempleo (%)",
    "fuerza_trabajo": "Fuerza de trabajo (miles de personas)",
    "ocupados": "Ocupados (miles de personas)",
    "desocupados": "Desocupados (miles de personas)",
    "imacec": "IMACEC",
    "ipsa_indice_real": "IPSA - índice real (sin datos 2019-2026)",
    "ipsa_etf": "IPSA - vía ETF (tendencia continua, no el índice puro)",
    "tipo_cambio": "Tipo de cambio (USD/CLP)",
    "eof_tpm_proxima_reunion": "Expectativa TPM próxima reunión (EOF, %)",
    "eof_inflacion_12m": "Expectativa inflación 12 meses (EOF, %)",
    "eof_tipo_cambio_7d": "Expectativa tipo de cambio 7 días (EOF)",
    "eeuu_desempleo": "EEUU - Tasa de desempleo (%)",
    "eeuu_inflacion": "EEUU - Inflación interanual (%)",
    "eeuu_pib_per_capita": "EEUU - PIB per cápita (miles de USD, PPA)",
    "pib_chile": "PIB Chile (miles de millones de $, trimestral, desestacionalizado)",
    "pib_deflactor": "Deflactor del PIB (índice, 2018=100)",
    "sp500": "S&P 500 (EEUU)",
}

# Definiciones breves para el glosario. Solo para conceptos que no son obvios
# por el nombre (no hace falta explicar "tipo de cambio").
DEFINICIONES = {
    "tpm": "Tasa de Política Monetaria: la tasa de interés de referencia que fija el Banco Central para la economía. Sube para enfriar la inflación, baja para estimular la actividad.",
    "ipc_variacion_mensual": "Variación del Índice de Precios al Consumidor respecto al mes anterior: la inflación mensual.",
    "desempleo": "Tasa de desocupación: Desocupados / Fuerza de trabajo, en porcentaje.",
    "fuerza_trabajo": "Personas de 15 años o más que están trabajando (ocupadas) o buscando trabajo activamente (desocupadas). No incluye a quienes no buscan empleo (estudiantes, jubilados, etc.).",
    "ocupados": "Personas de la fuerza de trabajo que tienen un empleo, remunerado o no, durante el período de referencia.",
    "desocupados": "Personas de la fuerza de trabajo que no tienen empleo pero buscaron trabajo activamente en las últimas semanas.",
    "imacec": "Índice Mensual de Actividad Económica: un proxy mensual del PIB, mide qué tan activa está la economía en su conjunto.",
    "ipsa_indice_real": "Índice de Precios Selectivo de Acciones: el principal índice bursátil de Chile, mide el desempeño de las acciones más transadas.",
    "eof_tpm_proxima_reunion": "Lo que los operadores financieros encuestados por el Banco Central esperan que sea la TPM en la próxima reunión de política monetaria.",
    "eof_inflacion_12m": "Lo que los operadores financieros esperan que sea la inflación acumulada en los próximos 12 meses.",
    "eof_tipo_cambio_7d": "Lo que los operadores financieros esperan que sea el tipo de cambio 7 días después de la fecha de la encuesta.",
    "eeuu_pib_per_capita": "Producto Interno Bruto dividido por la población, en miles de dólares ajustados por paridad de poder de compra (PPA). Dato anual.",
    "pib_chile": "Valor de todos los bienes y servicios producidos en Chile en el trimestre, a precios de mercado.",
    "pib_deflactor": "Mide cuánto suben los precios de TODO lo que se produce en el país (no solo lo que consumen las personas, como el IPC). Su variación interanual es una medida de inflación alternativa al IPC.",
    "sp500": "Índice de las 500 mayores empresas que cotizan en bolsa en Estados Unidos. El principal termómetro del mercado accionario estadounidense.",
}

# Agrupación temática, para no mostrar todo como una lista plana: cada categoría
# junta las tarjetas y los gráficos de sus series, más los indicadores calculados
# que le corresponden (definidos en series_utils.COMPUTADOS), y se muestra como
# un bloque desplegable (colapsado por defecto salvo la primera).
CATEGORIAS = [
    {
        "nombre": "Inflación y Política Monetaria",
        "series": ["ipc_variacion_mensual", "pib_deflactor", "tpm", "eof_tpm_proxima_reunion", "eof_inflacion_12m"],
        "computados": ["inflacion_acumulada", "inflacion_interanual", "inflacion_deflactor", "tpm_real"],
    },
    {
        "nombre": "Empleo",
        "series": ["desempleo", "fuerza_trabajo", "ocupados", "desocupados"],
        "computados": [],
    },
    {
        "nombre": "Actividad Económica",
        "series": ["imacec", "pib_chile"],
        "computados": ["imacec_interanual"],
    },
    {
        "nombre": "Mercado Financiero",
        "series": ["ipsa_indice_real", "ipsa_etf", "tipo_cambio", "eof_tipo_cambio_7d"],
        "computados": [],
    },
    {
        "nombre": "Estados Unidos",
        "series": ["eeuu_desempleo", "eeuu_inflacion", "eeuu_pib_per_capita", "sp500"],
        "computados": [],
    },
]
