"""Actualiza el dashboard con la última información disponible, con un solo comando.

    python actualizar.py          (o doble clic en actualizar.command)

Qué hace:
  1. Dispara en GitHub el workflow "Actualizar datos" (el mismo que corre solo cada día), que baja los
     datos nuevos del Banco Central / INE / FRED / Banco Mundial, archiva las revisiones de períodos
     anteriores en data/revisiones.csv, regenera docs/index.html y lo publica.
  2. Espera a que termine.
  3. Trae el resultado a esta copia local (git pull) y muestra un resumen: últimas fechas de las series
     principales y qué valores pasados cambiaron (revisiones).

Los valores anteriores nunca se pierden: cada vez que una fuente revisa una cifra, el valor viejo queda
en data/revisiones.csv junto con la fecha en que se detectó el cambio.

Requiere la CLI de GitHub (`gh`) instalada y con sesión iniciada (`gh auth login`).
"""

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent
HISTORICO = RAIZ / "data" / "historico.csv"
REVISIONES = RAIZ / "data" / "revisiones.csv"
WORKFLOW = "Actualizar datos"
URL_STREAMLIT = "https://datos-economicos-chile.streamlit.app"
URL_HTML = "https://sebam123.github.io/datos-economicos/"
ESPERA_MAXIMA_S = 15 * 60
SONDEO_S = 10

# (serie, etiqueta, unidad) -- lo que se muestra en el resumen final
SERIES_RESUMEN = [
    ("ipc_v12", "IPC (var. interanual)", "%"),
    ("imacec", "IMACEC (índice)", ""),
    ("desempleo", "Desempleo", "%"),
    ("tpm", "TPM", "%"),
    ("tipo_cambio", "Tipo de cambio (CLP/USD)", ""),
]


def ejecutar(comando: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(comando, cwd=RAIZ, capture_output=True, text=True, **kwargs)


def salir(mensaje: str) -> None:
    print(f"\n✗ {mensaje}")
    sys.exit(1)


def verificar_gh() -> None:
    if shutil.which("gh") is None:
        salir("No encuentro la CLI de GitHub (`gh`). Instálala con `brew install gh` y corre `gh auth login`.")
    if ejecutar(["gh", "auth", "status"]).returncode != 0:
        salir("`gh` no tiene sesión iniciada. Corre `gh auth login` y vuelve a intentar.")


def revisiones_actuales() -> set[tuple]:
    if not REVISIONES.exists():
        return set()
    r = pd.read_csv(REVISIONES)
    return set(zip(r["serie"], r["fecha"], r["valor_anterior"].round(9), r["valor_nuevo"].round(9)))


def disparar_workflow() -> int:
    """Dispara el workflow y devuelve el id de la corrida recién creada."""
    desde = datetime.now(timezone.utc) - timedelta(seconds=5)
    r = ejecutar(["gh", "workflow", "run", WORKFLOW, "--ref", "main"])
    if r.returncode != 0:
        salir(f"No pude disparar el workflow:\n{r.stderr.strip()}")
    print(f"✓ Workflow «{WORKFLOW}» disparado en GitHub.")

    for _ in range(30):
        time.sleep(3)
        r = ejecutar(
            ["gh", "run", "list", "--workflow", WORKFLOW, "--event", "workflow_dispatch", "--limit", "5",
             "--json", "databaseId,createdAt"]
        )
        if r.returncode != 0:
            continue
        for corrida in json.loads(r.stdout):
            creada = datetime.fromisoformat(corrida["createdAt"].replace("Z", "+00:00"))
            if creada >= desde:
                return corrida["databaseId"]
    salir("El workflow se disparó pero no encuentro la corrida. Revisa la pestaña Actions del repositorio.")


def esperar(id_corrida: int) -> dict:
    inicio = time.time()
    while time.time() - inicio < ESPERA_MAXIMA_S:
        r = ejecutar(["gh", "run", "view", str(id_corrida), "--json", "status,conclusion,url"])
        if r.returncode == 0:
            estado = json.loads(r.stdout)
            minutos, segundos = divmod(int(time.time() - inicio), 60)
            print(f"\r  esperando... {estado['status']:<12} ({minutos}:{segundos:02d})", end="", flush=True)
            if estado["status"] == "completed":
                print()
                return estado
        time.sleep(SONDEO_S)
    salir(f"Pasaron {ESPERA_MAXIMA_S // 60} minutos y el workflow sigue corriendo. Revisa la pestaña Actions.")


def mostrar_fallo(id_corrida: int) -> None:
    r = ejecutar(["gh", "run", "view", str(id_corrida), "--log-failed"])
    cola = "\n".join(r.stdout.strip().splitlines()[-25:])
    print(f"\nÚltimas líneas del log que falló:\n{cola}")


def traer_cambios() -> None:
    r = ejecutar(["git", "pull", "--rebase", "--autostash", "origin", "main"])
    if r.returncode != 0:
        salir(
            "El workflow terminó bien, pero no pude traer los cambios a esta copia (probablemente hay cambios "
            f"locales en conflicto):\n{r.stderr.strip()}"
        )
    print("✓ Copia local actualizada.")


def resumen(antes: set[tuple]) -> None:
    historico = pd.read_csv(HISTORICO, parse_dates=["fecha"])
    print("\nÚltimos datos:")
    for serie, etiqueta, unidad in SERIES_RESUMEN:
        datos = historico[historico["serie"] == serie].sort_values("fecha")
        if datos.empty:
            continue
        ultimo = datos.iloc[-1]
        print(f"  {etiqueta:<28} {ultimo['valor']:>10,.2f}{unidad}   ({ultimo['fecha']:%d-%m-%Y})")

    nuevas = revisiones_actuales() - antes
    if not nuevas:
        print("\nRevisiones: ningún período anterior cambió en esta corrida.")
        return
    print(f"\nRevisiones: {len(nuevas)} valores anteriores cambiaron (el valor viejo quedó archivado en data/revisiones.csv):")
    por_serie: dict[str, int] = {}
    for serie, *_ in nuevas:
        por_serie[serie] = por_serie.get(serie, 0) + 1
    for serie, n in sorted(por_serie.items(), key=lambda kv: -kv[1])[:10]:
        print(f"  {serie:<32} {n} períodos")


def main() -> None:
    verificar_gh()
    antes = revisiones_actuales()
    id_corrida = disparar_workflow()
    estado = esperar(id_corrida)
    if estado["conclusion"] != "success":
        mostrar_fallo(id_corrida)
        salir(f"El workflow terminó con estado «{estado['conclusion']}». Detalle: {estado['url']}")
    print(f"✓ Workflow terminado con éxito ({estado['url']}).")
    traer_cambios()
    resumen(antes)
    print(f"\nListo. Dashboard:\n  {URL_STREAMLIT}\n  {URL_HTML}")
    print("(GitHub Pages y Streamlit pueden tardar uno o dos minutos en reflejar el cambio.)")


if __name__ == "__main__":
    main()
