"""Rutas de recursos y datos, validas tanto en desarrollo como empaquetado
con PyInstaller (.exe).

- Recursos de solo lectura (config XML de Aplifisa): junto al codigo en
  desarrollo; dentro del bundle (sys._MEIPASS) en el .exe.
- Datos del usuario (ajustes, logs): %APPDATA%\\FacturasAplifisa.
"""

from __future__ import annotations

import os
import sys


def es_frozen() -> bool:
    return getattr(sys, "frozen", False)


def dir_recursos() -> str:
    """Carpeta que contiene config/ (XML de columnas de Aplifisa)."""
    if es_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ruta_config(nombre_xml: str) -> str:
    return os.path.join(dir_recursos(), "config", nombre_xml)


def dir_datos() -> str:
    """Carpeta de datos del usuario (se crea si no existe)."""
    base = os.environ.get("APPDATA", os.path.expanduser("~"))
    ruta = os.path.join(base, "FacturasAplifisa")
    os.makedirs(ruta, exist_ok=True)
    return ruta
