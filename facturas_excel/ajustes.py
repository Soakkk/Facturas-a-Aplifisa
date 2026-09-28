"""Ajustes del programa, en la base de datos local (almacen.py).

Almacen tonto a proposito (leer / guardar una clave): lo usan el escaneo
(carpeta, escaner, ppp), el control de gasto de Gemini, los divisores de la
ventana… La primera vez se copian los de %APPDATA%\\FacturasAplifisa\\ajustes.json,
que queda como estaba.
"""

from __future__ import annotations

import os
from typing import Any

from .rutas import dir_datos

_FICHERO = "ajustes.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _col():
    from .almacen import Coleccion
    return Coleccion("ajustes", dir_datos(), legado=_ruta())


def leer_todo() -> dict:
    return _col().leer_todo()


def leer(clave: str, por_defecto: Any = None) -> Any:
    valor = _col().leer(clave)
    return por_defecto if valor is None else valor


def guardar(clave: str, valor: Any) -> None:
    """Solo cambia esa clave: asi no se pisa lo de nadie."""
    _col().guardar(clave, valor)   # no poder recordarlo no debe tumbar la app
