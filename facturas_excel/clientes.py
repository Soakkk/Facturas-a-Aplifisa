"""Lo que hay que recordar de cada cliente de la asesoria, por NIF.

De momento solo si esta en RECARGO DE EQUIVALENCIA (no deduce IVA: sus gastos se
registran por el total de la factura). Se guarda en %APPDATA%\\FacturasAplifisa
para no tener que marcarlo en cada lote.
"""

from __future__ import annotations

import json
import os
import unicodedata
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


def _clave_nombre(nombre) -> str:
    """Nombre comparable sin acentos, puntuación ni forma societaria."""
    texto = "".join(
        c for c in unicodedata.normalize("NFD", str(nombre or ""))
        if unicodedata.category(c) != "Mn"
    ).upper()
    for caracter in ",.()-_/":
        texto = texto.replace(caracter, " ")
    tokens = [t for t in texto.split()
              if t not in {"SL", "SLU", "SA", "SAU", "CB"}]
    return " ".join(tokens)


def buscar_confirmado_por_nombre(nombre: str) -> tuple[str, str] | None:
    """Cliente confirmado cuyo nombre coincide con el leído en la factura."""
    clave = _clave_nombre(nombre)
    if not clave:
        return None
    coincidencias = []
    for nif, ficha in _leer_todo().items():
        if (isinstance(ficha, dict) and ficha.get("confirmado")
                and _clave_nombre(ficha.get("nombre")) == clave):
            coincidencias.append((_normaliza(nif), ficha.get("nombre", "")))
    return coincidencias[0] if len(coincidencias) == 1 else None


# --------------------------------------------------- regimen de recargo
# Dos clientes pueden comprar los dos con recargo de equivalencia y llevarse de
# forma distinta, porque lo que manda es SU regimen, no la factura:
#   - MINORISTA en recargo (no presenta el 303): no deduce IVA, asi que el gasto
#     se registra por el TOTAL de la factura, sin desglose.
#   - MAYORISTA en estimacion directa: SI registra el IVA y el recargo por
#     separado, con su desglose normal.
TOTAL = "total"          # minorista: un apunte por el total factura
DESGLOSE = "desglose"    # mayorista: base, IVA y recargo cada uno en lo suyo


def regimen_recargo(nif) -> str:
    """Como se registran las facturas con recargo de este cliente.

    Devuelve TOTAL, DESGLOSE, o "" si aun no se ha dicho (entonces hay que
    preguntarlo: no se puede acertar por las buenas).
    """
    nif = _normaliza(nif)
    if not nif:
        return ""
    ficha = _leer_todo().get(nif, {})
    guardado = ficha.get("regimen_recargo")
    if guardado in (TOTAL, DESGLOSE):
        return guardado
    # Compatibilidad con la casilla de antes (era un si/no).
    if ficha.get("recargo_equivalencia"):
        return TOTAL
    return ""


def guardar_regimen_recargo(nif, regimen: str, nombre: str = "") -> None:
    nif = _normaliza(nif)
    if not nif or regimen not in (TOTAL, DESGLOSE, ""):
        return
    todo = _leer_todo()
    ficha = todo.setdefault(nif, {})
    ficha["regimen_recargo"] = regimen
    ficha["recargo_equivalencia"] = (regimen == TOTAL)   # por si lo lee algo viejo
    if nombre:
        ficha["nombre"] = nombre
    try:
        with open(_ruta(), "w", encoding="utf-8") as fh:
            json.dump(todo, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass
