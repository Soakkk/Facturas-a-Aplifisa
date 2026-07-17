"""Memoria de NIF de proveedores, compartida por TODOS los clientes.

Hay CIF que vienen impresos en un margen, en letra diminuta o de refilon, y se
leen mal o no se leen. En cuanto uno se sabe bien (porque se leyo nitido en una
factura o porque lo escribio una persona), no hay que volver a averiguarlo: se
guarda en %APPDATA%\\FacturasAplifisa\\proveedores.json y sirve para el resto de
lotes y de clientes.

Almacen tonto a proposito: la clave la calcula quien llama (procesar.py, que es
quien sabe normalizar nombres). Asi no hay import circular.
"""

from __future__ import annotations

import json
import os
from typing import Dict, Optional

from .rutas import dir_datos

_FICHERO = "proveedores.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def leer_todo() -> Dict[str, dict]:
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):  # no existe todavia o esta corrupto
        return {}


def leer(clave: str) -> Optional[dict]:
    """{'nif', 'nombre', 'manual'} de un proveedor, o None si no se conoce."""
    if not clave:
        return None
    ficha = leer_todo().get(clave)
    return ficha if isinstance(ficha, dict) and ficha.get("nif") else None


def guardar(clave: str, nif: str, nombre: str = "", manual: bool = False) -> bool:
    """Recuerda el NIF de un proveedor. Devuelve si se guardo algo.

    Lo escrito a mano por una persona MANDA: no lo pisa despues una lectura
    automatica (que es justo lo que suele venir mal).
    """
    if not clave or not nif:
        return False
    todo = leer_todo()
    ficha = todo.get(clave)
    if isinstance(ficha, dict) and ficha.get("manual") and not manual:
        return False
    todo[clave] = {"nif": nif, "nombre": nombre or (ficha or {}).get("nombre", ""),
                   "manual": bool(manual) or bool((ficha or {}).get("manual"))}
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=2, ensure_ascii=False, sort_keys=True)
        return True
    except OSError:
        return False  # no poder recordarlo no debe tumbar la app
