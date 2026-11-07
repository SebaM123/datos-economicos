"""Titulados de educación superior de Chile 2007-2025 (Mineduc / SIES): resumen para la pestaña «Profesionales y técnicos» del Monitor.

Los datos son los archivos «Titulados Ed Superior AAAA» de https://datosabiertos.mineduc.cl/titulados-en-educacion-superior/ : un CSV por año con un
registro por título obtenido (con el identificador anonimizado del estudiante). Pesan ~2,2 GB descomprimidos, así que NO se procesan en el pipeline
automático: este script se corre a mano cuando el Mineduc publica un año nuevo (cada septiembre más o menos) y deja un resumen de ~150 KB en
docs/monitor/data/titulados.json. Nada individual (ni MRUN) pasa al resumen: solo conteos.

Uso:  python procesar_titulados.py CARPETA
donde CARPETA contiene los .rar bajados (T2007.rar, ..., o cualquier nombre con el año) o los CSV ya extraídos (se buscan *.csv de forma recursiva).
Los .rar se abren con bsdtar (viene con macOS/Anaconda: `bsdtar -xf archivo.rar -C destino`).

Qué cuenta cada cosa
  - técnico: «Técnico de Nivel Superior»; profesional: «Profesional con/sin licenciatura»; posgrado: magíster, doctorado y especialidades médicas u odontológicas;
    diplomados y postítulos: aparte (no son una profesión nueva: los hace quien ya tiene un título); licenciatura sin título: grado no conducente a título.
  - Se cuentan TÍTULOS, no personas: quien obtiene dos títulos en el año aparece dos veces. Las «personas» son MRUN distintos.
  - «Carrera» = categoría genérica del SIES (AREA_GENERICA, ~275 categorías que agrupan los nombres propios de cada institución).
  - «Programa nuevo» = nombre de programa (normalizado) que nunca había tenido titulados en el sistema; se descartan planes especiales, de continuidad y de
    segunda titulación, que son vías para quienes ya tienen un título. Puede ser un cambio de nombre y no una profesión realmente nueva.
"""

import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

import pandas as pd

SALIDA = Path(__file__).resolve().parent.parent / "docs" / "monitor" / "data" / "titulados.json"
COLUMNAS = ["mrun", "gen_alu", "rango_edad", "tipo_inst_2", "nivel_carrera_1", "nomb_carrera", "region_sede", "area_conocimiento", "area_generica", "modalidad", "nomb_inst"]
NIVEL = {
    "Técnico de Nivel Superior": "tecnico", "Profesional Con Licenciatura": "profesional", "Profesional Sin Licenciatura": "profesional",
    "Magister": "posgrado", "Doctorado": "posgrado", "Especialidad Médica U Odontológica": "posgrado",
    "Postítulo": "postitulo", "Diplomado (desde un semestre)": "postitulo", "Licenciatura No Conducente a Título": "licenciatura",
}
NIVELES = ["tecnico", "profesional", "posgrado", "postitulo", "licenciatura"]
INSTITUCION = {"Centros de Formación Técnica": "CFT", "Institutos Profesionales": "IP", "Universidades CRUCH": "Universidad CRUCH", "Universidades Privadas": "Universidad privada"}
EDADES = ["15 a 19 Años", "20 a 24 Años", "25 a 29 Años", "30 a 34 Años", "35 a 39 Años", "40 y más años"]
# Vías para quienes ya tienen un título: no son profesiones nuevas
NO_NUEVO = re.compile(r"PLAN ESPECIAL|PLAN DE CONTINUIDAD|CONTINUIDAD DE ESTUDIOS|PROSECUCION|SEGUNDA TITULACION|SISTEMA ESPECIAL|PLAN COMPLEMENTARIO|PROGRAMA ESPECIAL|PLAN DE TITULACION|TITULACION ESPECIAL")
# Para mostrar nombres en mayúsculas sin tildes como texto normal
TILDES = {
    "electrico": "eléctrico", "electrica": "eléctrica", "mecanico": "mecánico", "hidraulico": "hidráulico", "automatica": "automática", "informatica": "informática",
    "publico": "público", "publica": "pública", "economica": "económica", "clinica": "clínica", "pedagogico": "pedagógico", "analitica": "analítica", "organica": "orgánica",
    "ejecucion": "ejecución", "cosmetica": "cosmética", "diagnostico": "diagnóstico", "tecnicas": "técnicas", "tecnicos": "técnicos", "cientifico": "científico",
    "ingenieria": "ingeniería", "pedagogia": "pedagogía", "educacion": "educación", "administracion": "administración", "tecnico": "técnico",
    "tecnologia": "tecnología", "computacion": "computación", "informacion": "información", "comunicacion": "comunicación", "gestion": "gestión",
    "mencion": "mención", "analisis": "análisis", "basica": "básica", "enfermeria": "enfermería", "psicologia": "psicología",
    "kinesiologia": "kinesiología", "nutricion": "nutrición", "construccion": "construcción", "electronica": "electrónica", "mecanica": "mecánica",
    "geologia": "geología", "agricola": "agrícola", "quimica": "química", "biologia": "biología", "fisica": "física", "matematica": "matemática",
    "medico": "médico", "prevencion": "prevención", "produccion": "producción", "logistica": "logística", "estetica": "estética", "optica": "óptica",
    "parvulos": "párvulos", "diseno": "diseño", "ensenanza": "enseñanza", "accion": "acción", "creacion": "creación",
    "automatizacion": "automatización", "mineria": "minería", "programacion": "programación", "gastronomia": "gastronomía",
    "fotografia": "fotografía", "odontologia": "odontología", "fonoaudiologia": "fonoaudiología", "juridica": "jurídica", "juridico": "jurídico",
    "cientifica": "científica", "tecnica": "técnica", "sicologia": "sicología", "economia": "economía", "geografia": "geografía",
    "filosofia": "filosofía", "musica": "música", "hoteleria": "hotelería", "agronomia": "agronomía", "sociologia": "sociología",
    "antropologia": "antropología", "religion": "religión", "linguistica": "lingüística", "traduccion": "traducción", "orientacion": "orientación",
    "rehabilitacion": "rehabilitación", "terapeutica": "terapéutica", "radiologia": "radiología", "imagenologia": "imagenología",
    "biotecnologia": "biotecnología", "bioquimica": "bioquímica", "estadistica": "estadística", "topografia": "topografía",
    "cartografia": "cartografía", "hidraulica": "hidráulica", "energia": "energía", "refrigeracion": "refrigeración",
    "climatizacion": "climatización", "mantencion": "mantención", "cosmetologia": "cosmetología", "peluqueria": "peluquería",
    "bibliotecologia": "bibliotecología",
}


def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().upper()
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9 ]", " ", s)).strip()


def _bonito(texto: str) -> str:
    """'INGENIERIA EN OPERACIONES LOGISTICAS' -> 'Ingeniería en operaciones logísticas'."""
    palabras = _normalizar(texto).lower().split()
    palabras = [TILDES.get(p) or (TILDES[p[:-1]] + "s" if p.endswith("s") and p[:-1] in TILDES else p) for p in palabras]
    palabras = [p[:-4] + "ción" if p.endswith("cion") else p[:-4] + "sión" if p.endswith("sion") else p for p in palabras]
    s = " ".join(palabras)
    return s[:1].upper() + s[1:]


def _anio(nombre: str) -> str | None:
    """Año del nombre de un archivo (el último número de 4 cifras: los CSV del Mineduc empiezan con una fecha AAAAMMDD)."""
    años = re.findall(r"(?<!\d)(20\d\d)(?!\d)", nombre)
    return años[-1] if años else None


ACRONIMOS = {"IP", "CFT", "AIEP", "UC", "DUOC", "UDLA", "UTEM", "USACH", "UNAB", "UCSH", "UTFSM", "UDP", "INACAP", "UBB", "UCN", "UFT", "UNIACC", "UST", "UV", "UCM", "PUCV", "IACC", "UCV"}
CONECTORES = {"DE", "DEL", "LA", "LAS", "LOS", "EL", "Y", "E", "EN", "A"}


def _institucion(texto: str) -> str:
    """'UNIVERSIDAD DE CHILE' -> 'Universidad de Chile'; deja las siglas (IP, CFT, AIEP...) en mayúsculas."""
    s = " ".join(w if w in ACRONIMOS else w.lower() if w in CONECTORES else w.capitalize() for w in str(texto).split())
    for sin, con in (("Tomas", "Tomás"), ("Andres", "Andrés"), ("Maria", "María"), ("Concepcion", "Concepción"), ("Valparaiso", "Valparaíso"), ("Catolica", "Católica"),
                     ("Tecnica", "Técnica"), ("Tecnologica", "Tecnológica"), ("Sebastian", "Sebastián"), ("Raul", "Raúl"), ("Henriquez", "Henríquez"), ("Ibanez", "Ibáñez"),
                     ("Bio Bio", "Bío-Bío"), ("Biobio", "Biobío"), ("Araucania", "Araucanía"), ("Los Leones", "Los Leones"), ("Mayor", "Mayor"), ("Fernando", "Fernando")):
        s = s.replace(sin, con)
    return s[:1].upper() + s[1:] if not s.startswith(("IP", "CFT")) else s


def _csvs(carpeta: Path) -> dict[int, Path]:
    """Un CSV por año. Si hay .rar sin extraer, los extrae a una carpeta temporal con bsdtar."""
    archivos = {}
    for rar in sorted(carpeta.rglob("*.rar")):
        anio = _anio(rar.name)
        if anio and not any(_anio(c.name) == anio for c in carpeta.rglob("*.csv")):
            destino = Path(tempfile.mkdtemp(prefix=f"titulados{anio}_"))
            subprocess.run(["bsdtar", "-xf", str(rar), "-C", str(destino)], check=True)
            archivos[int(anio)] = next(destino.glob("*.csv"))
    for csv in carpeta.rglob("*.csv"):
        if _anio(csv.name):
            archivos[int(_anio(csv.name))] = csv
    return dict(sorted(archivos.items()))


def main(carpeta: Path) -> None:
    csvs = _csvs(carpeta)
    if not csvs:
        raise SystemExit(f"No encontré CSV ni .rar de titulados en {carpeta}")
    anios = sorted(csvs)
    if anios != list(range(anios[0], anios[-1] + 1)):
        raise SystemExit(f"Faltan años: tengo {anios}")
    d = pd.concat([pd.read_csv(csvs[a], sep=";", usecols=COLUMNAS, dtype=str, encoding="utf-8").assign(anio=a) for a in anios], ignore_index=True)
    d["nivel"] = d["nivel_carrera_1"].map(NIVEL)
    if d["nivel"].isna().any():
        raise SystemExit(f"Hay niveles no reconocidos: {sorted(d.loc[d['nivel'].isna(), 'nivel_carrera_1'].unique())}")
    d["inst"] = d["tipo_inst_2"].map(INSTITUCION)
    d["mujer"] = d["gen_alu"] == "2"
    d["norm"] = d["nomb_carrera"].map(_normalizar)
    tp = d[d["nivel"].isin(["tecnico", "profesional"])]  # carreras técnicas y profesionales

    def por_anio(df: pd.DataFrame, clave=None) -> dict | list:
        if clave is None:
            return [int((df["anio"] == a).sum()) for a in anios]
        tabla = df.groupby([clave, "anio"]).size().unstack(fill_value=0).reindex(columns=anios, fill_value=0)
        return {str(k): [int(v) for v in fila] for k, fila in tabla.iterrows()}

    salida: dict = {"anios": anios, "fuente": "Mineduc, Servicio de Información de Educación Superior (SIES)", "ultimo_anio": anios[-1]}
    salida["niveles"] = {n: por_anio(d[d["nivel"] == n]) for n in NIVELES}

    # personas distintas (MRUN) con título técnico o profesional: por año y acumuladas desde el primer año de la base
    vistos: set = set()
    por_persona, acumuladas = [], []
    for a in anios:
        m = set(tp.loc[tp["anio"] == a, "mrun"])
        por_persona.append(len(m))
        vistos |= m
        acumuladas.append(len(vistos))
    salida["personas"] = {"por_anio": por_persona, "acumuladas": acumuladas}

    salida["instituciones"] = {n: por_anio(d[(d["nivel"] == n) & d["inst"].notna()], "inst") for n in ("tecnico", "profesional", "posgrado")}
    salida["areas"] = {n: por_anio(d[d["nivel"] == n], "area_conocimiento") for n in ("tecnico", "profesional")}
    salida["mujeres"] = {n: [round(float(d[(d["nivel"] == n) & (d["anio"] == a)]["mujer"].mean() * 100), 1) for a in anios] for n in NIVELES[:4]}
    def no_presencial(df: pd.DataFrame, a: int) -> float | None:
        m = df.loc[df["anio"] == a, "modalidad"].dropna()  # los primeros años no informan la modalidad
        return round(float((m == "No Presencial").mean() * 100), 1) if len(m) > len(df[df["anio"] == a]) * 0.5 else None

    salida["no_presencial"] = {n: [no_presencial(d[d["nivel"] == n], a) for a in anios] for n in ("tecnico", "profesional")}
    salida["edades"] = {n: {e: [round(float(((x := d[(d["nivel"] == n) & (d["anio"] == a)])["rango_edad"] == e).sum() / max(1, len(x)) * 100), 1) for a in anios] for e in EDADES}
                        for n in ("tecnico", "profesional")}
    salida["regiones"] = {n: por_anio(d[d["nivel"] == n], "region_sede") for n in ("tecnico", "profesional")}

    # carreras (categoría genérica SIES), con su nivel dominante
    carreras = []
    for nombre, g in tp.groupby("area_generica"):
        nivel = g["nivel"].mode().iloc[0]
        ult = g[g["anio"] == anios[-1]]
        carreras.append({
            "n": str(nombre), "nivel": nivel, "area": str(g["area_conocimiento"].mode().iloc[0]),
            "t": por_anio(g), "mujeres": round(float(ult["mujer"].mean() * 100), 1) if len(ult) else None,
        })
    salida["carreras"] = sorted(carreras, key=lambda c: -c["t"][-1])

    # carreras nuevas: categorías genéricas que aparecen por primera vez, y programas con nombre nuevo
    primera_generica = tp.groupby("area_generica")["anio"].min()
    salida["nuevas_genericas"] = [{"n": str(n), "anio": int(a), "t": int(((tp["area_generica"] == n) & (tp["anio"] == anios[-1])).sum())}
                                  for n, a in primera_generica.items() if a > anios[0]]
    salida["nuevas_genericas"].sort(key=lambda x: (-x["anio"], x["n"]))
    primera_prog = tp.groupby("norm")["anio"].min()
    nuevos = {}
    for a in anios[1:]:
        nombres = primera_prog[primera_prog == a].index
        sub = tp[(tp["anio"] == a) & tp["norm"].isin(nombres) & ~tp["norm"].str.contains(NO_NUEVO)]
        resumen = sub.groupby("norm").agg(t=("mrun", "size"), crudo=("nomb_carrera", lambda s: s.mode().iloc[0]), inst=("nomb_inst", lambda s: s.mode().iloc[0]),
                                          nivel=("nivel", lambda s: s.mode().iloc[0]), area=("area_generica", lambda s: s.mode().iloc[0]))
        resumen = resumen.sort_values("t", ascending=False)
        nuevos[str(a)] = {
            "programas": int(len(resumen)), "titulados": int(resumen["t"].sum()), "pct": round(float(resumen["t"].sum() / max(1, (tp["anio"] == a).sum()) * 100), 2),
            "lista": [{"n": _bonito(r.crudo), "t": int(r.t), "inst": _institucion(r.inst), "nivel": r.nivel, "carrera": r.area}
                      for r in resumen.head(15).itertuples()],
        }
    salida["nuevos_programas"] = nuevos

    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Titulados: {len(d):,} registros 2007-{anios[-1]}, {len(carreras)} carreras, guardado en {SALIDA} ({SALIDA.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(Path(sys.argv[1]))
