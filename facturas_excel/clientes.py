"""Lo que hay que recordar de cada cliente de la asesoria, por NIF.

De momento solo si esta en RECARGO DE EQUIVALENCIA (no deduce IVA: sus gastos se
registran por el total de la factura). Se guarda en %APPDATA%\\FacturasAplifisa
para no tener que marcarlo en cada lote.
"""

from __future__ import annotations

import json
import os
from typing import Dict

from .rutas import dir_datos

_FICHERO = "clientes.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _leer_todo() -> Dict[str, dict]:
    try:
        with open(_ruta(), encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else {}
    except (OSError, ValueError):  # no existe todavia o esta corrupto
        return {}


def _normaliza(nif) -> str:
    return "".join(c for c in str(nif or "") if c.isalnum()).upper()


def en_recargo_equivalencia(nif) -> bool:
    nif = _normaliza(nif)
    if not nif:
        return False
    return bool(_leer_todo().get(nif, {}).get("recargo_equivalencia"))


def guardar_recargo_equivalencia(nif, activo: bool, nombre: str = "") -> None:
    nif = _normaliza(nif)
    if not nif:
        return
    todo = _leer_todo()
    ficha = todo.setdefault(nif, {})
    ficha["recargo_equivalencia"] = bool(activo)
    if nombre:
        ficha["nombre"] = nombre  # solo para poder leer el fichero a ojo
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass  # no poder recordarlo no debe tumbar la app


def nombres_conocidos() -> list:
    """Nombres de los clientes ya vistos, para no tener que escribirlos."""
    nombres = {ficha.get("nombre", "").strip()
               for ficha in _leer_todo().values() if isinstance(ficha, dict)}
    return sorted(n for n in nombres if n)


def recordar_nombre(nif, nombre: str) -> None:
    """Guarda el nombre del cliente aunque no este en recargo: sirve para
    proponerlo al escanear."""
    nif = _normaliza(nif)
    if not nif or not nombre:
        return
    todo = _leer_todo()
    todo.setdefault(nif, {})["nombre"] = nombre
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def marcar_cliente(nif, nombre: str = "") -> None:
    """Deja constancia de que ESTE es un cliente de la asesoria, dicho por una
    persona. Vale mucho mas que cualquier deduccion automatica: la proxima vez
    que aparezca en un lote, gana el a cualquier otro NIF."""
    nif = _normaliza(nif)
    if not nif:
        return
    todo = _leer_todo()
    ficha = todo.setdefault(nif, {})
    ficha["confirmado"] = True
    if nombre:
        ficha["nombre"] = nombre
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def es_cliente_confirmado(nif) -> bool:
    nif = _normaliza(nif)
    return bool(nif and _leer_todo().get(nif, {}).get("confirmado"))
