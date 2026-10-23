"""Composición del PIB de Chile para el Monitor: tres «árboles» de componentes que se pueden recorrer hacia abajo.

  gasto           PIB = consumo + inversión + exportaciones - importaciones; las exportaciones se abren en bienes
                  (por producto: cobre, fruta, celulosa, salmón...) y servicios.
  actividad       PIB = suma del valor agregado de cada sector + impuestos (minería del cobre vs. otra minería, ramas de la
                  industria, comercio, servicios...).
  exportaciones   exportaciones de bienes por producto, en dólares y con datos mensuales hasta el último mes publicado.

Todo a PRECIOS CORRIENTES (nominal) y como AÑO MÓVIL (suma de los últimos 4 trimestres, o 12 meses en exportaciones): así la
estacionalidad no distorsiona y cada punto es comparable con el resto. Ojo: al ser nominal, cuando sube el precio del cobre sube su
peso en el PIB aunque no se produzca más.

Datos: data/composicion.csv (ver data_pipeline/fetch_composicion.py). Salida: docs/monitor/data/composicion/<arbol>.json
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

COMPOSICION_PATH = Path(__file__).resolve().parent.parent / "data" / "composicion.csv"
SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "composicion"

# Un componente "Otros" se crea si el resto de un nodo (nodo menos la suma de sus hijos) pesa más que esto dentro del nodo,
# al menos en algún período.
UMBRAL_RESTO = 0.004


@dataclass
class Nodo:
    id: str
    nombre: str
    valor: pd.Series | None = None  # None: se calcula como la suma de sus hijos
    hijos: list["Nodo"] = field(default_factory=list)
    estimado: bool = False


def _serie(datos: pd.DataFrame, nombre: str) -> pd.Series:
    s = datos[datos["serie"] == nombre].set_index("fecha")["valor"].sort_index()
    return s[~s.index.duplicated(keep="last")]


def _expandir(nodo: Nodo, avisos: list[str], resto_siempre: bool = False) -> None:
    """Agrega a cada nodo un hijo «Otros» con la diferencia entre el nodo y la suma de sus hijos (si es relevante)."""
    for hijo in nodo.hijos:
        _expandir(hijo, avisos)
    if not nodo.hijos or nodo.valor is None:
        return
    suma = pd.concat([h.valor for h in nodo.hijos], axis=1).sum(axis=1, min_count=1)
    resto = (nodo.valor - suma).dropna()
    if resto.empty:
        return
    peso = (resto / nodo.valor.reindex(resto.index)).replace([np.inf, -np.inf], np.nan)
    if peso.min() < -0.01:
        avisos.append(f"{nodo.id}: los hijos superan al nodo hasta en {abs(peso.min()):.1%}")
    if (peso > UMBRAL_RESTO).any():
        nodo.hijos.append(Nodo(f"{nodo.id}__otros", f"Otros ({nodo.nombre})", resto.clip(lower=0), estimado=True))


def _completar_valores(nodo: Nodo) -> pd.Series:
    """Los nodos sin valor propio valen la suma de sus hijos."""
    for hijo in nodo.hijos:
        _completar_valores(hijo)
    if nodo.valor is None:
        nodo.valor = pd.concat([h.valor for h in nodo.hijos], axis=1).sum(axis=1, min_count=len(nodo.hijos))
    return nodo.valor


def _aplanar(nodo: Nodo, padre: str | None, fechas: pd.DatetimeIndex, salida: dict) -> None:
    valores = nodo.valor.reindex(fechas)
    salida[nodo.id] = {
        "n": nodo.nombre, "p": padre, "h": [h.id for h in nodo.hijos], "e": nodo.estimado,
        "v": [None if pd.isna(x) else round(float(x), 2) for x in valores],
    }
    for hijo in nodo.hijos:
        _aplanar(hijo, nodo.id, fechas, salida)


# ---------- Exportaciones de bienes por producto ----------
# (código del Banco Central, nombre, hijos)
ARBOL_EXPORTACIONES = ("Z", "Exportaciones de bienes", [
    ("A", "Minería", [
        ("A1", "Cobre", [("A2", "Cátodos de cobre", []), ("A3", "Concentrados de cobre", [])]),
        ("A8", "Carbonato de litio", []), ("A4", "Hierro", []), ("A6", "Oro", []), ("A5", "Plata", []),
        ("A7", "Concentrado de molibdeno", []), ("A9", "Sal", []),
    ]),
    ("B", "Agropecuario, silvícola y pesquero", [
        ("B1", "Fruta fresca", [("B11", "Uvas", []), ("B12", "Manzanas", []), ("B13", "Peras", []), ("B14", "Arándanos", []),
                                ("B15", "Kiwis", []), ("B16", "Ciruelas", []), ("B17", "Cerezas", []), ("B18", "Paltas", [])]),
        ("B2", "Otros agropecuarios", [("B21", "Semilla de maíz", []), ("B22", "Semilla de hortalizas", [])]),
        ("B3", "Silvícola", []), ("B4", "Pesca extractiva", []),
    ]),
    ("C", "Industriales", [
        ("C1", "Alimentos", [("C13", "Salmón", []), ("C14", "Trucha", []), ("C11", "Harina de pescado", []), ("C1E", "Aceite de pescado", []),
                             ("C15", "Merluza", []), ("C16", "Conservas de pescado", []), ("C17", "Moluscos y crustáceos", []),
                             ("C18", "Fruta deshidratada", []), ("C19", "Fruta congelada", []), ("C1A", "Jugo de fruta", []),
                             ("C1B", "Fruta en conserva", []), ("C1C", "Carne de ave", []), ("C1D", "Carne de cerdo", [])]),
        ("C2", "Bebidas y tabaco", [("C22", "Vino embotellado", []), ("C23", "Vino a granel y otros", []), ("C24", "Bebidas no alcohólicas", [])]),
        ("C3", "Forestal y muebles de madera", [("C31", "Madera aserrada", []), ("C32", "Chips de madera", []), ("C33", "Madera perfilada", []),
                                                ("C34", "Tableros de fibra", []), ("C35", "Madera contrachapada", [])]),
        ("C4", "Celulosa, papel y otros", [("C42", "Celulosa blanqueada de conífera", []), ("C43", "Celulosa blanqueada de eucalipto", []),
                                           ("C44", "Cartulina", []), ("C45", "Celulosa cruda de conífera", [])]),
        ("C5", "Productos químicos", [("C51", "Metanol", []), ("C52", "Yodo", []), ("C53", "Nitrato de potasio", []), ("C53A", "Abonos", []),
                                      ("C55", "Óxido de molibdeno", []), ("C56", "Neumáticos", []), ("C58A", "Hidróxido de litio", []),
                                      ("C58B", "Sulfato de litio", [])]),
        ("C6", "Industria metálica básica", [("C61", "Ferromolibdeno", []), ("C62", "Alambre de cobre", [])]),
        ("C7", "Maquinaria y equipos", [("C71", "Manufacturas metálicas", []), ("C72", "Maquinaria y equipos", []), ("C73", "Material de transporte", [])]),
        ("C9", "Otros productos industriales", []),
    ]),
])


def _nodo_exportaciones(t: tuple, series: dict[str, pd.Series], prefijo: str) -> Nodo:
    codigo, nombre, hijos = t
    return Nodo(f"{prefijo}{codigo}", nombre, series.get(codigo), [_nodo_exportaciones(h, series, prefijo) for h in hijos])


def _anio_movil(s: pd.Series, ventana: int) -> pd.Series:
    return s.rolling(ventana).sum().dropna()


def _sumar_trimestres(s: pd.Series) -> pd.Series:
    """Mensual -> trimestral, solo trimestres con sus 3 meses."""
    g = s.resample("QS")
    return g.sum()[g.count() == 3]


def _escribir(arbol: dict) -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / f"{arbol['id']}.json").write_text(json.dumps(arbol, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def _armar(id_: str, nombre: str, raiz: Nodo, ventana: int, frecuencia: str, unidad: str, descripcion: str, avisos: list[str]) -> dict:
    _completar_valores(raiz)  # primero los totales intermedios (nodos sin valor propio) y recién después los «Otros»
    _expandir(raiz, avisos)
    fechas = raiz.valor.dropna().index
    nodos: dict = {}
    _aplanar(raiz, None, fechas, nodos)
    return {
        "id": id_, "nombre": nombre, "raiz": raiz.id, "frecuencia": frecuencia, "unidad": unidad, "descripcion": descripcion,
        "fechas": [f.strftime("%Y-%m-%d") for f in fechas], "nodos": nodos,
    }


def construir_composicion() -> list[str]:
    """Genera los tres árboles. Devuelve avisos de consistencia (hijos que no suman su padre)."""
    if not COMPOSICION_PATH.exists():
        return ["No existe data/composicion.csv"]
    datos = pd.read_csv(COMPOSICION_PATH, parse_dates=["fecha"])
    avisos: list[str] = []
    S = lambda nombre: _serie(datos, nombre)  # noqa: E731

    # Exportaciones de bienes en US$ millones, mensual (año móvil de 12 meses)
    usd = {c: S(f"x_{c}") for c in {t for t in _codigos(ARBOL_EXPORTACIONES)} if not S(f"x_{c}").empty}
    tc = S("tc_promedio_mensual")
    ultimo_mes = usd["Z"].index.max()

    # ---- Árbol de exportaciones (US$, año móvil 12 meses)
    usd12 = {c: _anio_movil(s, 12) for c, s in usd.items()}
    raiz_x = _nodo_exportaciones(ARBOL_EXPORTACIONES, usd12, "xu_")
    _escribir(_armar(
        "exportaciones", "Exportaciones de bienes por producto", raiz_x, 12, "M", "millones de US$ (año móvil de 12 meses)",
        "Exportaciones de bienes (FOB) de los últimos 12 meses, en dólares corrientes, según la balanza de pagos del Banco Central. "
        "«Otros» es lo que no aparece desglosado dentro de cada grupo.", avisos))

    # ---- Convertir exportaciones a pesos (dólar promedio de cada mes) y pasar a trimestres: miles de millones de $
    en_pesos = {c: _sumar_trimestres(s * tc.reindex(s.index) / 1000.0) for c, s in usd.items()}
    pesos4 = {c: _anio_movil(s, 4) for c, s in en_pesos.items()}

    # ---- Árbol de gasto (miles de millones de $, año móvil de 4 trimestres)
    g = {n: _anio_movil(S(n), 4) for n in datos["serie"].unique() if n.startswith("g_")}
    bienes = _nodo_exportaciones(ARBOL_EXPORTACIONES, pesos4, "xb_")
    bienes.nombre = "Bienes"
    servicios = Nodo("g_servicios", "Servicios y otros (estimado)", (g["g_exportaciones"] - pesos4["Z"].reindex(g["g_exportaciones"].index)).dropna(), estimado=True)
    importaciones = Nodo("g_importaciones", "Importaciones (se restan)", -g["g_importaciones"])
    raiz_g = Nodo("g_pib", "PIB", g["g_pib"], [
        Nodo("g_consumo", "Consumo total", None, [
            Nodo("g_consumo_privado", "Consumo de los hogares", g["g_consumo_privado"], [
                Nodo("g_consumo_durables", "Bienes durables", g["g_consumo_durables"]),
                Nodo("g_consumo_no_durables", "Bienes no durables", g["g_consumo_no_durables"]),
                Nodo("g_consumo_servicios", "Servicios", g["g_consumo_servicios"]),
            ]),
            Nodo("g_consumo_gobierno", "Consumo del gobierno", g["g_consumo_gobierno"]),
        ]),
        Nodo("g_inversion", "Inversión", None, [
            Nodo("g_fbcf", "Inversión fija (formación bruta de capital fijo)", g["g_fbcf"], [
                Nodo("g_fbcf_construccion", "Construcción y otras obras", g["g_fbcf_construccion"]),
                Nodo("g_fbcf_maquinaria", "Maquinaria y equipos", g["g_fbcf_maquinaria"]),
            ]),
            Nodo("g_existencias", "Variación de existencias", g["g_existencias"]),
        ]),
        Nodo("g_exportaciones", "Exportaciones de bienes y servicios", g["g_exportaciones"], [bienes, servicios]),
        importaciones,
    ])
    _escribir(_armar(
        "gasto", "PIB por gasto (demanda)", raiz_g, 4, "T", "miles de millones de $ corrientes (año móvil de 4 trimestres)",
        "Cómo se reparte el PIB entre quienes lo demandan: hogares, gobierno, inversión y el resto del mundo (exportaciones menos importaciones). "
        "Las exportaciones de bienes se abren por producto convirtiendo los dólares de la balanza de pagos a pesos con el dólar promedio de "
        "cada mes; «Servicios y otros» es la diferencia con las exportaciones de las cuentas nacionales (estimación, incluye servicios y "
        "diferencias de medición).", avisos))

    # ---- Árbol por actividad (miles de millones de $, año móvil de 4 trimestres)
    a = {n: _anio_movil(S(n), 4) for n in datos["serie"].unique() if n.startswith("a_")}
    raiz_a = Nodo("a_pib", "PIB", g["g_pib"], [
        Nodo("a_agro", "Agropecuario-silvícola", a["a_agro"]),
        Nodo("a_pesca", "Pesca", a["a_pesca"]),
        Nodo("a_mineria", "Minería", a["a_mineria"], [
            Nodo("a_mineria_cobre", "Minería del cobre", a["a_mineria_cobre"]), Nodo("a_mineria_otra", "Otra minería", a["a_mineria_otra"])]),
        Nodo("a_industria", "Industria manufacturera", a["a_industria"], [
            Nodo("a_ind_alimentos", "Alimentos, bebidas y tabaco", a["a_ind_alimentos"]),
            Nodo("a_ind_celulosa", "Celulosa, papel e imprentas", a["a_ind_celulosa"]),
            Nodo("a_ind_quimica", "Química, petróleo, caucho y plástico", a["a_ind_quimica"]),
            Nodo("a_ind_metalmecanica", "Productos metálicos, maquinaria y equipo", a["a_ind_metalmecanica"]),
            Nodo("a_ind_minerales", "Minerales no metálicos y metálica básica", a["a_ind_minerales"]),
            Nodo("a_ind_madera", "Maderas y muebles", a["a_ind_madera"]),
            Nodo("a_ind_textil", "Textil, vestuario, cuero y calzado", a["a_ind_textil"]),
        ]),
        Nodo("a_ega", "Electricidad, gas y agua", a["a_ega"]),
        Nodo("a_construccion", "Construcción", a["a_construccion"]),
        Nodo("a_comercio", "Comercio, restaurantes y hoteles", a["a_comercio"]),
        Nodo("a_transporte_com", "Transporte y comunicaciones", None, [
            Nodo("a_transporte", "Transporte", a["a_transporte"]), Nodo("a_comunicaciones", "Comunicaciones", a["a_comunicaciones"])]),
        Nodo("a_serv_empresariales", "Servicios financieros y empresariales", a["a_serv_empresariales"]),
        Nodo("a_vivienda", "Servicios de vivienda", a["a_vivienda"]),
        Nodo("a_serv_personales", "Servicios personales", a["a_serv_personales"]),
        Nodo("a_admin_publica", "Administración pública", a["a_admin_publica"]),
        Nodo("a_impuestos", "Impuestos sobre los productos", a["a_impuestos"]),
    ])
    _escribir(_armar(
        "actividad", "PIB por actividad (sectores)", raiz_a, 4, "T", "miles de millones de $ corrientes (año móvil de 4 trimestres)",
        "Cuánto aporta cada sector al PIB (valor agregado a precios corrientes) más los impuestos sobre los productos. A precios corrientes: "
        "cuando sube el precio del cobre sube el peso de la minería aunque no se produzca más.", avisos))
    return avisos


def _codigos(t: tuple) -> list[str]:
    return [t[0]] + [c for h in t[2] for c in _codigos(h)]


if __name__ == "__main__":
    for aviso in construir_composicion():
        print("AVISO:", aviso)
    print("Composición generada en", SALIDA)
