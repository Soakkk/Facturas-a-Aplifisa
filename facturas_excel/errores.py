"""Registro de fallos: errores.log en la carpeta de datos del programa.

En el .exe no hay consola, así que lo que falla se apunta aquí con la fecha,
la versión y el detalle técnico, para poder averiguar después qué pasó.
"""

from __future__ import annotations

import os
from datetime import datetime

FICHERO = "errores.log"


def apuntar(detalle: str) -> None:
    """Añade un fallo a errores.log. Nunca lanza: apuntar no debe fallar."""
    try:
        from . import __version__
        from .rutas import dir_datos
        with open(os.path.join(dir_datos(), FICHERO), "a", encoding="utf-8",
                  errors="replace") as fh:
            from .texto import escapar_invisibles
            fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] v{__version__}\n"
                     f"{escapar_invisibles(detalle)}")
    except Exception:
        pass
