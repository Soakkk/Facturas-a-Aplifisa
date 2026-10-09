"""Memoria de NIF de proveedores, compartida por TODOS los clientes.

Hay CIF que vienen impresos en un margen, en letra diminuta o de refilon, y se
leen mal o no se leen. En cuanto uno se sabe bien (porque se leyo nitido en una
factura o porque lo escribio una persona), no hay que volver a averiguarlo: se
guarda en la base de datos local (almacen.py) y sirve para el resto de
lotes y de clientes.

Almacen tonto a proposito: la clave la calcula quien llama (procesar.py, que es
quien sabe normalizar nombres). Asi no hay import circular.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from .rutas import dir_datos

_FICHERO = "proveedores.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _col():
    """Los proveedores, en la base de datos local (antes proveedores.json)."""
    from .almacen import Coleccion
    return Coleccion("proveedores", dir_datos(), legado=_ruta())


def leer_todo() -> Dict[str, dict]:
    return {k: v for k, v in _col().leer_todo().items() if isinstance(v, dict)}


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
    # Se completa la ficha, no se rehace: el nombre que puso una persona, su
    # cuenta y su subclave siguen ahí aunque se guarde otra vez el NIF.
    nueva = dict(ficha) if isinstance(ficha, dict) else {}
    nueva["nif"] = nif
    nombre = _nombre_guardable(nombre, nueva, nif)
    if not nueva.get("nombre_manual"):
        nueva["nombre"] = nombre or nueva.get("nombre", "")
    nueva["manual"] = bool(manual) or bool(nueva.get("manual"))
    todo[clave] = nueva
    return _col().guardar(clave, todo[clave])


def guardar_campos(clave: str, **campos) -> bool:
    """Anota lo que una PERSONA ha corregido de un proveedor.

    El nombre con el que se le llama, o la cuenta contable que le corresponde:
    lo que se escribe a mano vale para siempre y no lo pisa ninguna lectura
    automatica. Sin esto habria que corregir lo mismo en cada lote.
    """
    if not clave:
        return False
    todo = leer_todo()
    ficha = todo.get(clave)
    ficha = dict(ficha) if isinstance(ficha, dict) else {}
    if "nombre" in campos:
        nombre = _nombre_guardable(campos["nombre"], ficha, campos.get("nif"))
        # El nombre que puso una persona no lo pisa otro guardado (al cambiar
        # la cuenta se guarda también el nombre de la fila).
        if ficha.get("nombre_manual") and not campos.get("nombre_manual"):
            nombre = None
        campos = dict(campos, nombre=nombre)
    ficha.update({k: v for k, v in campos.items() if v not in (None, "")})
    todo[clave] = ficha
    return _col().guardar(clave, todo[clave])


def _nombre_guardable(nombre, ficha: dict, nif: str = ""):
    """Un nombre con un carácter invisible (una tilde mal copiada) no se
    guarda tal cual: se recupera la letra con los nombres ya guardados de ese
    NIF; si no se puede y la ficha ya tiene nombre, se queda ese; si no, el
    limpio."""
    from .texto import limpiar, reparar
    limpio, roto = limpiar(nombre)
    if not roto:
        return limpio
    nif = str(nif or (ficha or {}).get("nif") or "").upper()
    conocidos = [f.get("nombre") for f in leer_todo().values()
                 if nif and str(f.get("nif", "")).upper() == nif]
    recuperado = reparar(nombre, conocidos)
    if recuperado:
        return recuperado
    if str((ficha or {}).get("nombre") or "").strip():
        return None
    return limpio


def reponer(clave: str, ficha: Optional[dict]) -> bool:
    """Deja la ficha exactamente como estaba (para deshacer): sin ficha
    antes, se borra. `guardar_campos` no sirve: no quita campos."""
    if not clave:
        return False
    if ficha is None:
        return _col().borrar(clave)
    return _col().guardar(clave, dict(ficha))


def buscar_por_nif(nif: str) -> Optional[dict]:
    """La ficha de un proveedor a partir de su NIF (la clave es el nombre, y el
    nombre es justo lo que cambia de una factura a otra)."""
    return buscar_clave_por_nif(nif)[1]


def buscar_clave_por_nif(nif: str) -> tuple:
    """(clave, ficha) del proveedor con ese NIF, o (None, None).

    Lo que se recuerde de él se escribe en ESA clave: la que sale de su
    nombre deja de ser la suya en cuanto una persona le cambia el nombre (y
    entonces la cuenta iba a otra ficha que ya no se leía)."""
    if not nif:
        return None, None
    from .texto import tiene_invisibles
    todo = leer_todo()
    fichas = [(k, todo[k]) for k in sorted(todo)
              if isinstance(todo[k], dict)
              and str(todo[k].get("nif", "")).upper() == nif.upper()]
    if not fichas:
        return None, None
    # Si hay varias del mismo NIF: la sin caracteres rotos y, de esas, la que
    # tiene la cuenta puesta por una persona; si empatan, la primera por
    # clave, que es la que leía y escribía la 1.24 (así su memoria sigue
    # dando la misma cuenta). El nombre lo decide nombres_guardados.
    return max(fichas, key=lambda kf: (not tiene_invisibles(kf[1].get("nombre")),
                                       bool(kf[1].get("cuenta_manual"))))
