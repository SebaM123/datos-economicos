import os

import bcchapi
from dotenv import load_dotenv

load_dotenv()


def obtener_cliente() -> bcchapi.Siete:
    usuario = os.environ.get("BCCH_USER")
    contrasena = os.environ.get("BCCH_PASSWORD")
    if not usuario or not contrasena:
        raise RuntimeError(
            "Faltan las variables de entorno BCCH_USER / BCCH_PASSWORD. "
            "Definilas antes de correr este script (ver README.md)."
        )
    return bcchapi.Siete(usuario, contrasena)
