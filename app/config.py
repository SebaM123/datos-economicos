from pathlib import Path

HISTORICO_PATH = Path(__file__).resolve().parent.parent / "data" / "historico.csv"
PIB_ESTADOS_PATH = Path(__file__).resolve().parent.parent / "data" / "pib_por_estado_eeuu.json"
OCDE_PAISES_PATH = Path(__file__).resolve().parent.parent / "data" / "ocde_paises.json"

# Título y definición de cada comparación de la sección "Países OCDE" (ver
# data_pipeline/fetch_worldbank.py). Todas vienen del Banco Mundial, con la misma
# metodología entre países, así que pueden diferir un poco de los datos "oficiales"
# de Chile/EEUU (BCCh/INE/BLS) que se muestran en el resto del dashboard.
OCDE_INDICADORES = {
    "pib_per_capita_ppa": (
        "PIB per cápita, PPA (USD internacionales)",
        "Fuente: Banco Mundial. Metodología distinta a la serie 'PIB per cápita (PPA)' de más arriba "
        "(que usa datos del FMI-WEO vía BCCh) — los niveles pueden no calzar exacto, pero sirven para "
        "ubicar a Chile entre sus pares de la OCDE.",
    ),
    "desempleo": (
        "Tasa de desempleo (%)",
        "Fuente: Banco Mundial, estimación armonizada de la OIT (Organización Internacional del Trabajo). "
        "No es la tasa que publica el INE (que sí se usa en la sección Empleo) — está armonizada para "
        "que los países sean comparables entre sí.",
    ),
    "inflacion": (
        "Inflación anual (IPC, %)",
        "Fuente: Banco Mundial, variación del IPC promedio anual (no interanual a un mes específico como "
        "el resto del dashboard). Sirve como referencia de magnitud, no para comparar mes a mes.",
    ),
    "gini": (
        "Índice de Gini",
        "Mismo indicador y fuente (Banco Mundial) que el de la sección Desigualdad. Serie anual con huecos, "
        "no todos los países tienen encuesta de hogares todos los años.",
    ),
}

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
    "eeuu_pib_total": "EEUU - PIB total (miles de millones de USD)",
    "pib_chile": "PIB Chile (miles de millones de $, trimestral, desestacionalizado)",
    "pib_deflactor": "Deflactor del PIB (índice, 2018=100)",
    "sp500": "S&P 500 (EEUU)",
    "chile_pib_per_capita_ppa": "Chile - PIB per cápita (miles de USD, PPA)",
    "ipp_general": "Chile - IPP, índice de precios al productor (2019=100)",
    "eeuu_ipp": "EEUU - IPP, variación interanual (%)",
    "ipc_sae_variacion_mensual": "IPC SAE - variación mensual (%)",
    "pib_mineria": "PIB Minería (miles de millones de $, mensual, desestacionalizado)",
    "pib_no_minero": "PIB No minero (miles de millones de $, trimestral, desestacionalizado)",
    "chile_gini": "Chile - Índice de Gini",
    "eeuu_gini": "EEUU - Índice de Gini",
}

# Etiquetas cortas solo para la cinta animada (ticker): ahí no hay espacio para
# aclaraciones largas como "(sin datos 2019-2026)", que sí van en las tarjetas.
ETIQUETAS_TICKER = {
    "ipsa_indice_real": "IPSA",
    "tipo_cambio": "Dólar",
    "sp500": "S&P 500",
    "tpm": "TPM",
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
    "eeuu_pib_per_capita": "Producto Interno Bruto dividido por la población, en miles de dólares ajustados por paridad de poder de compra (PPA), fuente FMI-WEO. Comparable directamente con 'Chile - PIB per cápita', mismo origen y unidad. El año en curso es una estimación del FMI, no una cifra final.",
    "pib_chile": "Valor de todos los bienes y servicios producidos en Chile en el trimestre, a precios de mercado, en pesos chilenos. No es comparable en magnitud con las cifras 'per cápita' en dólares de más abajo — son unidades distintas.",
    "pib_deflactor": "Mide cuánto suben los precios de TODO lo que se produce en el país (no solo lo que consumen las personas, como el IPC). Su variación interanual es una medida de inflación alternativa al IPC.",
    "sp500": "Índice de las 500 mayores empresas que cotizan en bolsa en Estados Unidos. El principal termómetro del mercado accionario estadounidense.",
    "chile_pib_per_capita_ppa": "Producto Interno Bruto de Chile dividido por la población, en miles de dólares ajustados por paridad de poder de compra (PPA), fuente FMI-WEO. Mismo origen y unidad que 'EEUU - PIB per cápita', para comparar directamente entre países. El año en curso es una estimación del FMI, no una cifra final.",
    "eeuu_pib_total": "Producto Interno Bruto total de Estados Unidos, en miles de millones de dólares corrientes, fuente Reserva Federal (FRED). No es comparable en magnitud con las cifras 'per cápita' de más arriba — son unidades distintas.",
    "ipp_general": "Índice de Precios al Productor: mide cuánto cobran las empresas por lo que producen (a diferencia del IPC, que mide lo que paga el consumidor). Suele anticipar hacia dónde va la inflación al consumidor, porque esos mayores costos tienden a traspasarse con rezago.",
    "eeuu_ipp": "Variación en 12 meses del Índice de Precios al Productor de EEUU (todos los commodities). Mismo origen (BCCh, Economía Internacional) que el resto de las series de EEUU de esta sección.",
    "ipc_sae_variacion_mensual": "IPC Sin Alimentos y Energía ('inflación subyacente'): excluye los componentes más volátiles del IPC (combustibles, alimentos frescos) para ver la tendencia de fondo de los precios, sin el ruido de shocks puntuales.",
    "pib_mineria": "Producto Interno Bruto del sector minero (principalmente cobre), en volumen (términos reales). Muy influenciado por el precio y la producción de cobre, no por consumo interno.",
    "pib_no_minero": "Producto Interno Bruto excluyendo minería, en volumen (términos reales). Muestra cómo le va al resto de la economía (servicios, comercio, construcción, etc.) sin el efecto del cobre, que puede mover mucho el PIB total por sí solo.",
    "chile_gini": "Índice de Gini: mide la desigualdad de ingresos entre 0 (igualdad perfecta) y 100 (un solo hogar concentra todo el ingreso). Fuente: Banco Mundial, en base a encuestas de hogares (CASEN en Chile). Serie anual con huecos, no todos los años tienen encuesta.",
    "eeuu_gini": "Índice de Gini de Estados Unidos, mismo origen y metodología (Banco Mundial) que el de Chile, para comparar directamente el nivel de desigualdad entre ambos países.",
}

# Agrupación temática, para no mostrar todo como una lista plana: cada categoría
# junta las tarjetas y los gráficos de sus series, más los indicadores calculados
# que le corresponden (definidos en series_utils.COMPUTADOS), y se muestra como
# un bloque desplegable (colapsado por defecto salvo la primera).
CATEGORIAS = [
    {
        "nombre": "Inflación y Política Monetaria",
        "series": [
            "ipc_variacion_mensual",
            "ipc_sae_variacion_mensual",
            "pib_deflactor",
            "ipp_general",
            "eeuu_ipp",
            "tpm",
            "eof_tpm_proxima_reunion",
            "eof_inflacion_12m",
        ],
        "computados": [
            "inflacion_acumulada",
            "inflacion_interanual",
            "inflacion_subyacente_interanual",
            "inflacion_deflactor",
            "tpm_real",
        ],
    },
    {
        "nombre": "Empleo",
        "series": ["desempleo", "fuerza_trabajo", "ocupados", "desocupados"],
        "computados": [],
    },
    {
        "nombre": "Actividad Económica",
        "series": ["imacec", "pib_chile", "chile_pib_per_capita_ppa", "pib_mineria", "pib_no_minero"],
        "computados": ["imacec_interanual", "pib_mineria_interanual", "pib_no_minero_interanual"],
    },
    {
        "nombre": "Mercado Financiero",
        "series": ["ipsa_indice_real", "ipsa_etf", "tipo_cambio", "eof_tipo_cambio_7d"],
        "computados": [],
    },
    {
        "nombre": "Estados Unidos",
        "series": ["eeuu_desempleo", "eeuu_inflacion", "eeuu_pib_total", "eeuu_pib_per_capita", "sp500"],
        "computados": [],
    },
    {
        "nombre": "Desigualdad",
        "series": ["chile_gini", "eeuu_gini"],
        "computados": [],
    },
]
