"""Ajustes del programa, en %APPDATA%\\FacturasAplifisa\\ajustes.json.

Almacen tonto a proposito (leer / escribir un JSON pequeño): lo usan el
escaneo (carpeta, escaner, ppp) y el control de gasto de Gemini. Comparte
fichero con `pendientes.py`, que solo toca su propia clave.
"""

from __future__ import annotations

import json
import os
from typing import Any

from .rutas import dir_datos

_FICHERO = "ajustes.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def leer_todo() -> dict:
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):   # no existe todavia o esta corrupto
        return {}


def leer(clave: str, por_defecto: Any = None) -> Any:
    valor = leer_todo().get(clave)
    return por_defecto if valor is None else valor


def guardar(clave: str, valor: Any) -> None:
    """Lee-modifica-escribe el fichero entero: asi no se pisa lo de nadie."""
    datos = leer_todo()
    datos[clave] = valor
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(datos, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass  # no poder recordar un ajuste no debe tumbar la app
