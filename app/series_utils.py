import numpy as np
import pandas as pd
import plotly.graph_objects as go

# Series de expectativas (EOF): el valor de una fecha es el pronóstico que hizo
# el mercado ESE día para un momento futuro, no un dato vigente de esa fecha.
# Acá se define, para cada una, cómo describir el horizonte del pronóstico.
DESCRIPCION_HORIZONTE_EOF = {
    "eof_tpm_proxima_reunion": "para la próxima reunión de política monetaria",
    "eof_inflacion_12m": "para los 12 meses siguientes",
    "eof_tipo_cambio_7d": "para 7 días después",
}


def describir_fecha_kpi(serie: str, fecha: pd.Timestamp) -> str:
    """Texto para mostrar bajo el valor de una tarjeta KPI. Para series de
    expectativas (EOF), aclara que es un pronóstico hecho en esa fecha para
    un momento posterior (que puede ya haber pasado), en vez de dar a entender
    que el dato es vigente a hoy.
    """
    horizonte = DESCRIPCION_HORIZONTE_EOF.get(serie)
    if horizonte:
        return f"pronóstico del {fecha.strftime('%d-%m-%Y')}, {horizonte}"
    return f"al {fecha.strftime('%d-%m-%Y')}"


def calcular_inflacion_acumulada_anual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación acumulada del año calendario en curso: acumula las variaciones
    mensuales del IPC desde enero hasta el último mes disponible con datos.
    Devuelve (valor_porcentual, fecha_del_ultimo_mes_usado), o None si no hay
    ningún dato de IPC para el año en curso todavía.
    """
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha")
    if ipc.empty:
        return None

    anio_actual = pd.Timestamp.now().year
    ipc_anio = ipc[ipc["fecha"].dt.year == anio_actual]
    if ipc_anio.empty:
        return None

    factor = 1.0
    for valor in ipc_anio["valor"]:
        factor *= 1 + valor / 100
    acumulada = (factor - 1) * 100
    return acumulada, ipc_anio["fecha"].iloc[-1]


def _serie_mensual(historico: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Serie (fecha, valor) ordenada, reindexada a todos los meses (los faltantes
    quedan en NaN), para que desplazar 12 posiciones sea siempre "hace 12 meses"."""
    datos = historico[historico["serie"] == serie].sort_values("fecha")
    if datos.empty:
        return pd.DataFrame(columns=["fecha", "valor"])
    completa = datos.set_index("fecha")["valor"].asfreq("MS")
    return completa.rename("valor").rename_axis("fecha").reset_index()


def obtener_serie(historico: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Serie mensual (fecha/valor) sin meses vacíos, lista para graficar."""
    return _serie_mensual(historico, serie).dropna().reset_index(drop=True)


def calcular_interanual_mensual(historico: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Variación interanual (%) de una serie MENSUAL de nivel/índice, para todo el
    historial (columnas fecha/valor) -- la versión "serie completa" de
    calcular_interanual_generico, que solo devuelve el último dato."""
    datos = _serie_mensual(historico, serie)
    if datos.empty:
        return datos
    datos["valor"] = (datos["valor"] / datos["valor"].shift(12) - 1) * 100
    return datos.dropna().reset_index(drop=True)


def calcular_inflacion_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación interanual (12 meses) del IPC, el dato "titular" que se cita en
    medios. Usa la variación anual OFICIAL que publica el Banco Central
    (`ipc_v12`); componerla desde las variaciones mensuales (que vienen
    redondeadas a 1 decimal) se desvía hasta ~0,04 pp del dato oficial (ej. ago-2026:
    4,17% compuesto vs 4,13% oficial). Si la serie oficial no está al día se cae a
    la composición mensual.
    """
    ipc = historico[historico["serie"] == "ipc_variacion_mensual"].sort_values("fecha")
    if len(ipc) < 12:
        return None

    oficial = historico[historico["serie"] == "ipc_v12"].sort_values("fecha")
    if not oficial.empty and oficial["fecha"].iloc[-1] >= ipc["fecha"].iloc[-1]:
        return float(oficial["valor"].iloc[-1]), oficial["fecha"].iloc[-1]

    ultimos_12 = ipc.tail(12)
    factor = 1.0
    for valor in ultimos_12["valor"]:
        factor *= 1 + valor / 100
    interanual = (factor - 1) * 100
    return interanual, ultimos_12["fecha"].iloc[-1]


def calcular_imacec_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación del IMACEC respecto al mismo mes del año anterior (%),
    que es como habitualmente se reporta este indicador (no como índice puro).
    """
    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha")
    if len(imacec) < 13:
        return None

    actual = imacec.iloc[-1]
    hace_un_anio = imacec.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_inflacion_deflactor_pib(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del deflactor del PIB (4 trimestres): una medida
    de inflación alternativa al IPC, que cubre TODO lo que produce el país
    (incluye, por ejemplo, bienes de inversión y exportaciones, no solo lo
    que compran los hogares).
    """
    deflactor = historico[historico["serie"] == "pib_deflactor"].sort_values("fecha")
    if len(deflactor) < 5:
        return None

    actual = deflactor.iloc[-1]
    hace_un_anio = deflactor.iloc[-5]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_inflacion_subyacente_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Inflación interanual del IPC SAE (sin alimentos y energía, "inflación subyacente"),
    excluyendo los componentes más volátiles para ver la tendencia de fondo. Se calcula
    desde el ÍNDICE oficial (`ipc_sae_indice`: índice / índice de hace 12 meses), que no
    arrastra el error de redondeo de componer variaciones mensuales; si el índice no está
    al día, se compone la variación mensual (`ipc_sae_variacion_mensual`).
    """
    ipc_sae = historico[historico["serie"] == "ipc_sae_variacion_mensual"].sort_values("fecha")
    if len(ipc_sae) < 12:
        return None

    indice = calcular_interanual_mensual(historico, "ipc_sae_indice")
    if not indice.empty and indice["fecha"].iloc[-1] >= ipc_sae["fecha"].iloc[-1]:
        return float(indice["valor"].iloc[-1]), indice["fecha"].iloc[-1]

    ultimos_12 = ipc_sae.tail(12)
    factor = 1.0
    for valor in ultimos_12["valor"]:
        factor *= 1 + valor / 100
    interanual = (factor - 1) * 100
    return interanual, ultimos_12["fecha"].iloc[-1]


def calcular_pib_mineria_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del PIB de minería (mensual, real, desestacionalizado)."""
    pib_mineria = historico[historico["serie"] == "pib_mineria"].sort_values("fecha")
    if len(pib_mineria) < 13:
        return None

    actual = pib_mineria.iloc[-1]
    hace_un_anio = pib_mineria.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_pib_no_minero_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual del PIB no minero (trimestral, real, desestacionalizado):
    muestra cómo le va al resto de la economía (servicios, comercio, construcción, etc.)
    sin el efecto del cobre, que puede mover mucho el PIB total por sí solo.
    """
    pib_no_minero = historico[historico["serie"] == "pib_no_minero"].sort_values("fecha")
    if len(pib_no_minero) < 5:
        return None

    actual = pib_no_minero.iloc[-1]
    hace_un_anio = pib_no_minero.iloc[-5]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_tpm_real(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """TPM real ex-post: la tasa de política monetaria menos la inflación
    interanual. Indicador clásico de qué tan restrictiva/expansiva está
    la política monetaria (positivo = restrictiva, negativo = expansiva).
    """
    tpm = historico[historico["serie"] == "tpm"].sort_values("fecha")
    inflacion = calcular_inflacion_interanual(historico)
    if tpm.empty or inflacion is None:
        return None

    tpm_actual = tpm.iloc[-1]
    inflacion_valor, _ = inflacion
    return tpm_actual["valor"] - inflacion_valor, tpm_actual["fecha"]


def calcular_desempleo_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Diferencia interanual de la tasa de desempleo, en puntos porcentuales."""
    return calcular_diferencia_interanual_generico(historico, "desempleo")


def calcular_variacion_mensual_serie(historico: pd.DataFrame, serie: str) -> pd.DataFrame:
    """Variación mensual (%) de una serie mensual de nivel/índice, todo el historial
    (columnas fecha/valor). Solo tiene sentido sobre series DESESTACIONALIZADAS."""
    datos = _serie_mensual(historico, serie)
    if datos.empty:
        return datos
    datos["valor"] = datos["valor"].pct_change() * 100
    return datos.dropna().reset_index(drop=True)


def calcular_imacec_mensual_desestacionalizado(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    """Variación mensual (%) del IMACEC DESESTACIONALIZADO: la forma en que el Banco
    Central titula el dato ("el Imacec cayó X% respecto del mes anterior"). Solo tiene
    sentido sobre la serie ajustada por estacionalidad; el IMACEC original (`imacec`) se
    compara contra el mismo mes del año anterior."""
    datos = _serie_mensual(historico, "imacec_sa").dropna()
    if len(datos) < 2:
        return None
    variacion = (datos["valor"].iloc[-1] / datos["valor"].iloc[-2] - 1) * 100
    return variacion, datos["fecha"].iloc[-1]


def calcular_imacec_minero_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    datos = calcular_interanual_mensual(historico, "imacec_minero")
    return (float(datos["valor"].iloc[-1]), datos["fecha"].iloc[-1]) if not datos.empty else None


def calcular_imacec_no_minero_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    datos = calcular_interanual_mensual(historico, "imacec_no_minero")
    return (float(datos["valor"].iloc[-1]), datos["fecha"].iloc[-1]) if not datos.empty else None


# Contribución de cada sector a la variación interanual del IMACEC (publicada por el
# Banco Central, en puntos porcentuales; las 6 suman el total).
SECTORES_IMACEC = [
    ("imacec_c_minero", "Minería", "#e0a83a"),
    ("imacec_c_industria", "Industria", "#6c8cf0"),
    ("imacec_c_resto_bienes", "Resto de bienes", "#8fd19e"),
    ("imacec_c_comercio", "Comercio", "#e07a9d"),
    ("imacec_c_servicios", "Servicios", "#5ec4c4"),
    ("imacec_c_impuestos", "Impuestos", "#a9a9a9"),
]


def calcular_contribuciones_imacec(historico: pd.DataFrame) -> pd.DataFrame:
    """Tabla ancha (una columna por sector + "total") con la contribución de cada sector
    al crecimiento interanual del IMACEC. `total` es la suma de los 6 sectores, que
    coincide con la variación interanual oficial del IMACEC."""
    columnas = {}
    for serie, etiqueta, _ in SECTORES_IMACEC:
        datos = historico[historico["serie"] == serie].set_index("fecha")["valor"]
        if datos.empty:
            return pd.DataFrame()
        columnas[etiqueta] = datos
    ancho = pd.DataFrame(columnas).dropna().sort_index()
    ancho["total"] = ancho.sum(axis=1)
    return ancho


def aplicar_ventanas_temporales(fig: go.Figure, ventanas: tuple = (3, 5, None), inicial: int = 0) -> go.Figure:
    """Agrega botones de ventana temporal ("3 años", "5 años", "Todo") a un gráfico de series
    de tiempo, y abre en `ventanas[inicial]`. Cada botón fija el rango del eje X Y el del eje Y
    (calculado solo con los datos de esa ventana): si no, un episodio extremo como el COVID
    (±20 pp) fija la escala de todo el gráfico y los meses recientes, que son lo que más se
    mira, se ven diminutos. Funciona solo con Plotly (sin JavaScript propio), así que sirve
    igual en Streamlit y en el HTML estático."""
    fechas = pd.concat([pd.Series(pd.to_datetime(list(t.x))) for t in fig.data if t.x is not None])
    ultimo, primero = fechas.max(), fechas.min()

    def rangos(anios):
        desde = primero if anios is None else max(primero, ultimo - pd.DateOffset(years=anios))
        lo, hi = np.inf, -np.inf
        pos, neg = {}, {}
        for traza in fig.data:
            x = pd.to_datetime(pd.Series(list(traza.x)))
            y = pd.Series(list(traza.y), dtype=float)
            visible = (x >= desde).to_numpy()
            if isinstance(traza, go.Bar):
                for xi, yi in zip(x[visible], y[visible]):
                    if yi >= 0:
                        pos[xi] = pos.get(xi, 0.0) + yi
                    else:
                        neg[xi] = neg.get(xi, 0.0) + yi
                lo, hi = min(lo, 0.0), max(hi, 0.0)
            else:
                yv = y[visible].dropna()
                if not yv.empty:
                    lo, hi = min(lo, yv.min()), max(hi, yv.max())
        if pos:
            hi = max(hi, max(pos.values()))
        if neg:
            lo = min(lo, min(neg.values()))
        margen = (hi - lo) * 0.08 or 1.0
        x0 = desde - pd.Timedelta(days=20)
        x1 = ultimo + pd.Timedelta(days=20)
        return [x0.strftime("%Y-%m-%d"), x1.strftime("%Y-%m-%d")], [float(lo - margen), float(hi + margen)]

    botones = []
    for anios in ventanas:
        rx, ry = rangos(anios)
        botones.append(
            dict(label="Todo" if anios is None else f"{anios} años", method="relayout",
                 args=[{"xaxis.range": rx, "yaxis.range": ry}])
        )
    rx, ry = rangos(ventanas[inicial])
    fig.update_layout(
        xaxis_range=rx, yaxis_range=ry,
        updatemenus=[dict(type="buttons", direction="right", x=0.0, xanchor="left", y=1.14, yanchor="top",
                          buttons=botones, active=inicial, pad=dict(r=4, t=0),
                          bgcolor="rgba(124,143,240,0.18)",
                          bordercolor="rgba(124,143,240,0.5)", font=dict(size=11, color="#5c70d6"))],
    )
    return fig


def construir_figura_barras_apiladas(
    tabla: pd.DataFrame, componentes: list[tuple[str, str]], titulo: str, ytitulo: str, total: str | None = "total"
) -> go.Figure:
    """Barras apiladas (positivos arriba, negativos abajo) de `componentes` -- lista de
    (columna, color) -- con la columna `total` como línea blanca encima. `tabla` está
    indexada por fecha. Sirve para cualquier descomposición aditiva: contribución de cada
    sector al IMACEC, aporte del salario real y del empleo a la masa salarial, etc.
    Compartida entre Streamlit y el HTML."""
    fig = go.Figure()
    for columna, color in componentes:
        fig.add_trace(
            go.Bar(
                x=tabla.index, y=tabla[columna], name=columna, marker_color=color,
                hovertemplate=columna + ": %{y:+.2f}<extra></extra>",
            )
        )
    if total:
        fig.add_trace(
            go.Scatter(
                x=tabla.index, y=tabla[total], name="Total", mode="lines",
                line=dict(color="#ffffff", width=2), hovertemplate="Total: %{y:+.2f}<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="relative", title=titulo, xaxis_title="", yaxis_title=ytitulo, bargap=0.1,
        legend=dict(orientation="h", y=-0.15),
    )
    fig.add_hline(y=0, line_width=1, line_color="gray")
    return aplicar_ventanas_temporales(fig)


def construir_figura_contribuciones_imacec(contribuciones: pd.DataFrame) -> go.Figure:
    """Cuánto aportó (o restó) cada sector al crecimiento interanual del IMACEC: el gráfico
    clásico del Banco Central para ver QUÉ sector explica el crecimiento del mes."""
    return construir_figura_barras_apiladas(
        contribuciones, [(etiqueta, color) for _, etiqueta, color in SECTORES_IMACEC],
        "Contribución al crecimiento interanual del IMACEC, por sector (pp)", "puntos porcentuales",
    )


def construir_figura_lineas(
    series: dict[str, pd.DataFrame], titulo: str, ytitulo: str = "%", meta: float | None = None, ventana_inicial: int = 0
) -> go.Figure:
    """Figura de varias líneas (una por entrada de `series`: nombre -> DataFrame fecha/valor),
    con una referencia opcional (ej. la meta de inflación). Compartida entre Streamlit y HTML."""
    fig = go.Figure()
    for nombre, datos in series.items():
        if datos is None or datos.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=datos["fecha"], y=datos["valor"], name=nombre, mode="lines",
                hovertemplate=nombre + ": %{y:.2f}<extra></extra>",
            )
        )
    fig.update_layout(title=titulo, xaxis_title="", yaxis_title=ytitulo, legend=dict(orientation="h", y=-0.15))
    if meta is not None:
        fig.add_hline(y=meta, line_dash="dash", line_color="gray", annotation_text=f"Meta {meta:g}%", annotation_position="top left")
    return aplicar_ventanas_temporales(fig, inicial=ventana_inicial)


def construir_figura_barras_variacion(datos: pd.DataFrame, titulo: str, ytitulo: str = "%") -> go.Figure:
    """Barras verdes/rojas de una variación (%) mes a mes (ej. IMACEC desestacionalizado
    mensual). Igual que construir_figura_variacion_interanual pero con eje configurable."""
    fig = construir_figura_variacion_interanual(datos, titulo)
    fig.update_layout(yaxis_title=ytitulo)
    return fig


def calcular_masa_salarial_real(historico: pd.DataFrame) -> pd.DataFrame:
    """MASA SALARIAL REAL, APROXIMACIÓN PROPIA (el Banco Central/INE no publican una serie
    con ese nombre en la API): índice real de remuneraciones (INE, base 2023=100) x
    ocupados asalariados (ENE). Columnas: fecha, masa (índice, promedio 2023 = 100),
    interanual, remuneracion_yoy, empleo_yoy, aporte_remuneracion y aporte_empleo (pp;
    suman la variación interanual de la masa: la interacción gw*ge se reparte mitad y
    mitad). Limitaciones: la remuneración (IR) es por hora, así que no captura cambios en
    las horas trabajadas, y los ocupados asalariados incluyen asalariados informales que
    el IR podría no cubrir.
    """
    ir = _serie_mensual(historico, "remuneraciones_real").set_index("fecha")["valor"]
    emp = _serie_mensual(historico, "ocupados_asalariados").set_index("fecha")["valor"]
    if ir.empty or emp.empty:
        return pd.DataFrame()
    df = pd.DataFrame({"ir": ir, "emp": emp}).dropna()
    df = df.asfreq("MS")
    base_2023 = df.loc["2023-01-01":"2023-12-01", "emp"].mean()
    df["masa"] = df["ir"] * df["emp"] / base_2023
    gw = df["ir"] / df["ir"].shift(12) - 1
    ge = df["emp"] / df["emp"].shift(12) - 1
    gm = (1 + gw) * (1 + ge) - 1
    out = pd.DataFrame({
        "masa": df["masa"],
        "interanual": gm * 100,
        "remuneracion_yoy": gw * 100,
        "empleo_yoy": ge * 100,
        "aporte_remuneracion": (gw + gw * ge / 2) * 100,
        "aporte_empleo": (ge + gw * ge / 2) * 100,
    }).dropna()
    return out.rename_axis("fecha").reset_index()


def calcular_masa_salarial_real_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    masa = calcular_masa_salarial_real(historico)
    return (float(masa["interanual"].iloc[-1]), masa["fecha"].iloc[-1]) if not masa.empty else None


def calcular_ipc_componentes_interanual(historico: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Variación interanual (%) del IPC total y de sus aperturas analíticas del Banco
    Central, cada una como DataFrame fecha/valor. El IPC total y los agregados "sin
    volátiles"/bienes/servicios/volátiles son la variación anual OFICIAL publicada; el IPC
    SAE (subyacente) se calcula desde su índice oficial."""
    def oficial(serie: str) -> pd.DataFrame:
        return _serie_mensual(historico, serie).dropna().reset_index(drop=True)

    return {
        "IPC total": oficial("ipc_v12"),
        "IPC subyacente (SAE: sin alimentos ni energía)": calcular_interanual_mensual(historico, "ipc_sae_indice"),
        "IPC sin volátiles": oficial("ipc_sin_volatiles_v12"),
        "Bienes sin volátiles": oficial("ipc_bienes_sin_volatiles_v12"),
        "Servicios sin volátiles": oficial("ipc_servicios_sin_volatiles_v12"),
        "Volátiles": oficial("ipc_volatiles_v12"),
    }


# Registro de indicadores calculados (no son una serie cruda de historico.csv,
# se derivan de una o más series). "{year}" en la etiqueta se reemplaza por el
# año de la fecha del dato al momento de mostrarlo.
COMPUTADOS = {
    "inflacion_acumulada": ("Inflación acumulada {year}", calcular_inflacion_acumulada_anual),
    "inflacion_interanual": ("Inflación interanual (12 meses, IPC)", calcular_inflacion_interanual),
    "inflacion_deflactor": ("Inflación interanual (deflactor del PIB)", calcular_inflacion_deflactor_pib),
    "inflacion_subyacente_interanual": (
        "Inflación subyacente interanual (IPC SAE, 12 meses)",
        calcular_inflacion_subyacente_interanual,
    ),
    "imacec_interanual": ("IMACEC - variación interanual", calcular_imacec_interanual),
    "tpm_real": ("TPM real ex-post", calcular_tpm_real),
    "pib_mineria_interanual": ("PIB Minería - variación interanual", calcular_pib_mineria_interanual),
    "pib_no_minero_interanual": ("PIB No minero - variación interanual", calcular_pib_no_minero_interanual),
    "desempleo_interanual": ("Desempleo - variación interanual (puntos porcentuales)", calcular_desempleo_interanual),
    "imacec_sa_mensual": ("IMACEC desestacionalizado - variación mensual", calcular_imacec_mensual_desestacionalizado),
    "imacec_minero_interanual": ("IMACEC minero - variación interanual", calcular_imacec_minero_interanual),
    "imacec_no_minero_interanual": ("IMACEC no minero - variación interanual", calcular_imacec_no_minero_interanual),
    "masa_salarial_real_interanual": (
        "Masa salarial real (aprox.) - variación interanual",
        calcular_masa_salarial_real_interanual,
    ),
}


def estado_mas_parecido_a_chile(
    estados: dict, valor_chile: float, clave_valor: str = "pib_per_capita_usd"
) -> tuple[str, dict] | None:
    """De los estados de EEUU (ver fetch_fred.py y fetch_census.py), devuelve el
    código y los datos del que tiene el valor más cercano al de Chile en el
    indicador dado (`clave_valor`). Comparación aproximada, no exacta: cada
    indicador tiene su propia nota de metodología en la UI.
    """
    if not estados:
        return None
    return min(estados.items(), key=lambda item: abs(item[1][clave_valor] - valor_chile))


SERIES_EXPORTACIONES = ["exportaciones_mineria", "exportaciones_agropecuario", "exportaciones_industrial"]


def calcular_interanual_generico(historico: pd.DataFrame, serie: str) -> tuple[float, pd.Timestamp] | None:
    """Variación interanual (12 meses) de una serie mensual cualquiera: compara
    el último dato contra el mismo mes del año anterior, para no confundir
    estacionalidad (ej. la fruta exporta mucho más en verano) con una caída o
    alza real de la actividad.
    """
    datos = historico[historico["serie"] == serie].sort_values("fecha")
    if len(datos) < 13:
        return None
    actual = datos.iloc[-1]
    hace_un_anio = datos.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_total_exportaciones(historico: pd.DataFrame) -> pd.DataFrame:
    """Suma las exportaciones de bienes de los tres sectores (minería, agropecuario-
    silvícola-pesquero, industrial) por fecha. No incluye exportación de servicios.
    """
    disponibles = [s for s in SERIES_EXPORTACIONES if s in historico["serie"].unique()]
    pivote = historico[historico["serie"].isin(disponibles)].pivot(index="fecha", columns="serie", values="valor")
    pivote = pivote.dropna()
    total = pivote.sum(axis=1).reset_index()
    total.columns = ["fecha", "valor"]
    return total


def calcular_exportaciones_totales_interanual(historico: pd.DataFrame) -> tuple[float, pd.Timestamp] | None:
    total = calcular_total_exportaciones(historico)
    if len(total) < 13:
        return None
    actual = total.iloc[-1]
    hace_un_anio = total.iloc[-13]
    variacion = (actual["valor"] / hace_un_anio["valor"] - 1) * 100
    return variacion, actual["fecha"]


def calcular_diferencia_interanual_generico(historico: pd.DataFrame, serie: str) -> tuple[float, pd.Timestamp] | None:
    """Diferencia interanual EN PUNTOS de una serie mensual que ya es una tasa
    o porcentaje (ej. desempleo): valor actual menos el mismo mes del año
    anterior. A diferencia de calcular_interanual_generico (que da un % DE
    CAMBIO, apropiado para niveles/índices), acá tiene más sentido la
    diferencia en puntos — pasar de 8% a 9% de desempleo son "+1 punto",
    no "+12,5%".
    """
    datos = historico[historico["serie"] == serie].sort_values("fecha")
    if len(datos) < 13:
        return None
    actual = datos.iloc[-1]
    hace_un_anio = datos.iloc[-13]
    diferencia = actual["valor"] - hace_un_anio["valor"]
    return diferencia, actual["fecha"]


def calcular_anio_movil(datos_serie: pd.DataFrame, ventana: int = 12, operacion: str = "sum") -> pd.DataFrame:
    """Año móvil: agregado de los últimos `ventana` meses, recalculado en cada
    fecha (no solo a fin de año calendario). `datos_serie` debe venir ordenado
    por fecha, con columnas "fecha" y "valor".

    `operacion="sum"` (por defecto): para series de flujo aditivas y muy
    estacionales (ej. exportaciones en USD) — sumar los últimos 12 meses es
    la forma estándar de ver la tendencia de fondo sin que los picos/valles
    estacionales tapen si en realidad viene subiendo o bajando.

    `operacion="mean"`: para tasas o índices donde sumar 12 meses no tiene
    sentido (ej. tasa de desempleo: sumar da un número sin interpretación,
    promediar sí sirve para suavizar el ruido mes a mes).
    """
    datos_serie = datos_serie.sort_values("fecha")
    resultado = datos_serie[["fecha"]].copy()
    rolling = datos_serie["valor"].rolling(window=ventana)
    resultado["valor"] = rolling.mean() if operacion == "mean" else rolling.sum()
    return resultado.dropna().reset_index(drop=True)


def calcular_variacion_interanual_serie(datos_serie: pd.DataFrame, periodos: int = 12) -> pd.DataFrame:
    """Variación interanual (respecto a `periodos` observaciones atrás) de una
    serie YA agregada -- ej. la salida de calcular_anio_movil -- pensada para
    graficar la evolución completa en el tiempo, no solo el último dato (a
    diferencia de calcular_interanual_generico y afines, que solo devuelven
    el último valor para una tarjeta KPI).
    """
    datos_serie = datos_serie.sort_values("fecha").reset_index(drop=True)
    resultado = datos_serie[["fecha"]].copy()
    resultado["valor"] = (datos_serie["valor"] / datos_serie["valor"].shift(periodos) - 1) * 100
    return resultado.dropna().reset_index(drop=True)


def calcular_poblacion_mensual_interpolada(historico: pd.DataFrame) -> pd.DataFrame:
    """Población de Chile (Banco Mundial, anual) interpolada linealmente a
    frecuencia mensual, para poder dividir series mensuales (ej. IMACEC) por
    población. La población cambia muy poco de un mes a otro, así que
    interpolar linealmente entre los datos anuales es una aproximación
    razonable.

    El Banco Mundial suele publicar el dato del año en curso o del anterior
    (ej. población 2025 ya disponible en 2026), pero para los últimos meses
    de la muestra puede no haber todavía un punto anual posterior con el que
    interpolar -- se extrapolan hasta 2 años hacia adelante usando la tasa de
    crecimiento anual más reciente, para no dejar sin dato justo los meses
    más recientes (los más consultados).
    """
    poblacion = historico[historico["serie"] == "chile_poblacion"].sort_values("fecha")
    if len(poblacion) < 2:
        return pd.DataFrame(columns=["fecha", "valor"])

    serie = poblacion.set_index("fecha")["valor"]
    crecimiento_anual = serie.iloc[-1] / serie.iloc[-2] - 1
    fechas_extra = pd.date_range(serie.index.max() + pd.DateOffset(years=1), periods=2, freq="YS")
    valores_extra = [serie.iloc[-1] * (1 + crecimiento_anual) ** (i + 1) for i in range(len(fechas_extra))]
    serie_extendida = pd.concat([serie, pd.Series(valores_extra, index=fechas_extra)]).sort_index()

    rango_mensual = pd.date_range(serie_extendida.index.min(), serie_extendida.index.max(), freq="MS")
    serie_mensual = (
        serie_extendida.reindex(serie_extendida.index.union(rango_mensual))
        .sort_index()
        .interpolate(method="index")
        .reindex(rango_mensual)
    )
    return serie_mensual.rename("valor").rename_axis("fecha").reset_index()


def calcular_imacec_tendencia(historico: pd.DataFrame, ventana: int, per_capita: bool = False) -> pd.DataFrame:
    """PIB vía IMACEC: variación interanual del "año móvil" (promedio de los
    últimos `ventana` meses), para ver la tendencia de fondo del crecimiento
    sin el ruido mes a mes del IMACEC. `ventana=12` es el año móvil estándar;
    `ventana=48` (4 años) muestra una tendencia de más largo plazo.

    `per_capita=True` divide el IMACEC por la población interpolada
    mensualmente (ver calcular_poblacion_mensual_interpolada) ANTES de
    suavizar, para separar cuánto del crecimiento es "más gente" de cuánto
    es "más producto por persona" -- la comparación clásica entre PIB total
    y PIB per cápita.
    """
    imacec = historico[historico["serie"] == "imacec"].sort_values("fecha")
    if imacec.empty:
        return imacec

    if per_capita:
        poblacion = calcular_poblacion_mensual_interpolada(historico)
        if poblacion.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        combinado = imacec.merge(poblacion, on="fecha", suffixes=("", "_poblacion"))
        if combinado.empty:
            return pd.DataFrame(columns=["fecha", "valor"])
        combinado["valor"] = combinado["valor"] / combinado["valor_poblacion"]
        imacec = combinado[["fecha", "valor"]]

    suavizado = calcular_anio_movil(imacec, ventana=ventana, operacion="mean")
    return calcular_variacion_interanual_serie(suavizado)


def construir_figura_variacion_interanual(datos: pd.DataFrame, titulo: str) -> go.Figure:
    """Barras de una variación interanual (%) mes a mes, verde cuando es
    positiva y roja cuando es negativa: la forma habitual de mostrar el
    crecimiento del IMACEC. `datos` con columnas fecha/valor. Compartida
    entre Streamlit y el HTML estático (el HTML le aplica después el tema
    oscuro propio).
    """
    colores = ["#4ade80" if v >= 0 else "#f87171" for v in datos["valor"]]
    fig = go.Figure(
        go.Bar(
            x=datos["fecha"],
            y=datos["valor"],
            marker_color=colores,
            hovertemplate="%{x|%b %Y}: %{y:+.1f}%<extra></extra>",
        )
    )
    fig.update_layout(title=titulo, xaxis_title="", yaxis_title="%", bargap=0.15, showlegend=False)
    fig.add_hline(y=0, line_width=1, line_color="gray")
    return aplicar_ventanas_temporales(fig)


def construir_figura_ranking_ocde(datos_por_pais: dict, pais_destacado: str = "CHL") -> go.Figure:
    """Gráfico de barras horizontal comparando un indicador entre países de la OCDE
    (ver data_pipeline/fetch_worldbank.py), ordenado de menor a mayor, con Chile
    destacado en otro color para ubicarlo rápido entre sus pares.
    """
    filas = sorted(
        ((info["nombre"], info["valor"], codigo, info["anio"]) for codigo, info in datos_por_pais.items()),
        key=lambda fila: fila[1],
    )
    nombres = [fila[0] for fila in filas]
    valores = [fila[1] for fila in filas]
    anios = [fila[3] for fila in filas]
    colores = ["#7c8ff0" if fila[2] == pais_destacado else "#3a3f4f" for fila in filas]

    fig = go.Figure(
        go.Bar(
            x=valores,
            y=nombres,
            orientation="h",
            marker_color=colores,
            customdata=anios,
            hovertemplate="%{y}: %{x}<br>Año: %{customdata}<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(500, 24 * len(filas)),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    return fig


def insertar_huecos(datos_serie: pd.DataFrame, umbral_dias: int = 45) -> pd.DataFrame:
    """Inserta filas con valor nulo entre puntos separados por más de
    `umbral_dias`, para que los gráficos de línea corten en vez de unir
    con una recta dos fechas que en realidad no tienen datos entre medio.
    """
    filas = datos_serie.to_dict("records")
    resultado = []
    for i, fila in enumerate(filas):
        if i > 0:
            dias = (fila["fecha"] - filas[i - 1]["fecha"]).days
            if dias > umbral_dias:
                resultado.append({"fecha": filas[i - 1]["fecha"] + pd.Timedelta(days=1), "valor": None})
        resultado.append(fila)
    return pd.DataFrame(resultado)


def resumir_revisiones(revisiones: pd.DataFrame, nombres: dict[str, str], dias: int = 90) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resume el archivo de revisiones (ver data_pipeline/common.py): cada vez que el Banco
    Central u otra fuente oficial cambia un valor que ya teníamos, el valor anterior queda
    archivado. Devuelve (resumen, mayores_cambios) de los últimos `dias` días:
      - resumen: una fila por serie y día de detección, con cuántos períodos cambiaron.
      - mayores_cambios: los 15 cambios individuales más grandes (en %).
    """
    if revisiones.empty:
        return pd.DataFrame(), pd.DataFrame()
    rev = revisiones.copy()
    rev["detectado_el"] = pd.to_datetime(rev["detectado_el"])
    rev["fecha"] = pd.to_datetime(rev["fecha"])
    rev = rev[rev["detectado_el"] >= rev["detectado_el"].max() - pd.Timedelta(days=dias)]
    rev["cambio"] = rev["valor_nuevo"] - rev["valor_anterior"]
    rev["cambio_pct"] = np.where(rev["valor_anterior"] != 0, rev["cambio"] / rev["valor_anterior"].abs() * 100, np.nan)
    rev["Serie"] = rev["serie"].map(nombres).fillna(rev["serie"])

    resumen = (
        rev.groupby(["detectado_el", "Serie"])
        .agg(
            periodos=("fecha", "count"),
            desde=("fecha", "min"),
            hasta=("fecha", "max"),
            mayor_cambio_pct=("cambio_pct", lambda c: c.abs().max()),
        )
        .reset_index()
        .sort_values(["detectado_el", "mayor_cambio_pct"], ascending=[False, False])
    )
    resumen["detectado_el"] = resumen["detectado_el"].dt.strftime("%d-%m-%Y")
    resumen["desde"] = resumen["desde"].dt.strftime("%m-%Y")
    resumen["hasta"] = resumen["hasta"].dt.strftime("%m-%Y")
    resumen["mayor_cambio_pct"] = resumen["mayor_cambio_pct"].round(2)
    resumen = resumen.rename(columns={
        "detectado_el": "Detectado", "periodos": "Períodos revisados", "desde": "Desde", "hasta": "Hasta",
        "mayor_cambio_pct": "Mayor cambio (%)",
    })

    top = rev.reindex(rev["cambio_pct"].abs().sort_values(ascending=False).index).head(15)[
        ["Serie", "fecha", "valor_anterior", "valor_nuevo", "cambio_pct", "detectado_el"]
    ].copy()
    top["fecha"] = top["fecha"].dt.strftime("%m-%Y")
    top["detectado_el"] = top["detectado_el"].dt.strftime("%d-%m-%Y")
    top["cambio_pct"] = top["cambio_pct"].round(2)
    top["valor_anterior"] = top["valor_anterior"].round(3)
    top["valor_nuevo"] = top["valor_nuevo"].round(3)
    top = top.rename(columns={
        "fecha": "Período", "valor_anterior": "Valor anterior", "valor_nuevo": "Valor nuevo",
        "cambio_pct": "Cambio (%)", "detectado_el": "Detectado",
    })
    return resumen, top
