"""Lo que hay que recordar de cada cliente de la asesoria, por NIF.

De momento solo si esta en RECARGO DE EQUIVALENCIA (no deduce IVA: sus gastos se
registran por el total de la factura). Se guarda en %APPDATA%\\FacturasAplifisa
para no tener que marcarlo en cada lote.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Dict

from .rutas import dir_datos

_FICHERO = "clientes.json"


def _ruta() -> str:
    return os.path.join(dir_datos(), _FICHERO)


def _col():
    """Los clientes, en la base de datos local (antes clientes.json)."""
    from .almacen import Coleccion
    return Coleccion("clientes", dir_datos(), legado=_ruta())


def _leer_todo() -> Dict[str, dict]:
    return {k: v for k, v in _col().leer_todo().items() if isinstance(v, dict)}


def _guardar_ficha(nif: str, ficha: dict) -> None:
    _col().guardar(nif, ficha)   # si falla, no debe tumbar la app


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
    _guardar_ficha(nif, todo[nif])


def nombres_conocidos() -> list:
    """Nombres de los clientes ya vistos, para no tener que escribirlos.

    Incluye los del directorio comun de la suite (los mismos que usan los
    demas programas de la asesoria)."""
    from . import suite
    nombres = {ficha.get("nombre", "").strip()
               for ficha in _leer_todo().values() if isinstance(ficha, dict)}
    nombres.update(suite.nombres())
    # Un nombre roto que guardó la 1.24 (una tilde mal copiada) no se propone.
    nombres = {n for n in nombres if n and not _roto(n)}
    return sorted(n for n in nombres if n)


def _roto(nombre) -> bool:
    from .texto import tiene_invisibles
    return tiene_invisibles(nombre)


def recordar_nombre(nif, nombre: str) -> None:
    """Guarda el nombre del cliente aunque no este en recargo: sirve para
    proponerlo al escanear."""
    nif = _normaliza(nif)
    if not nif or not nombre or _roto(nombre):
        return
    todo = _leer_todo()
    todo.setdefault(nif, {})["nombre"] = nombre
    _guardar_ficha(nif, todo[nif])


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
    if nombre and not _roto(nombre):
        ficha["nombre"] = nombre
    _guardar_ficha(nif, todo[nif])
    # Lo confirmado por una persona se comparte con el resto de la suite.
    from . import suite
    suite.registrar_cliente(nif, nombre)


def es_cliente_confirmado(nif) -> bool:
    """Confirmado aqui por una persona, o cliente del directorio de la suite."""
    return Directorio().es_confirmado(nif)


def nombre_confirmado(nif) -> str:
    """El nombre con el que la asesoria conoce a este cliente."""
    return Directorio().nombre_confirmado(nif)


def nombre_guardado(nif) -> str:
    """El nombre que se guardó de este cliente, confirmado o no (sin uno
    roto)."""
    ficha = _leer_todo().get(_normaliza(nif), {}) if nif else {}
    nombre = ficha.get("nombre") if isinstance(ficha, dict) else ""
    return "" if not isinstance(nombre, str) or _roto(nombre) else nombre.strip()


def mismo_nombre(uno, otro) -> bool:
    """Si dos nombres son el mismo con el criterio de los clientes (sin
    tildes, puntuación, guiones ni forma societaria)."""
    clave = _clave_nombre(uno)
    return bool(clave) and clave == _clave_nombre(otro)


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
    return Directorio().buscar_por_nombre(nombre)


class Directorio:
    """Los clientes tal como están ahora, leídos una sola vez.

    Para analizar un lote entero: se preguntaba por cada nombre y cada NIF
    leídos (dos por hoja) y cada pregunta abría la base de datos y, para
    buscar por nombre, normalizaba los nombres de todos los clientes. Con
    450 hojas era casi un segundo por bloque, y más cuantos más clientes
    tuviera la asesoría. Las respuestas son las de siempre."""

    def __init__(self):
        from . import suite
        self._todo = _leer_todo()
        self._suite = suite.nombres_por_nif()
        self._por_nombre = None

    def es_confirmado(self, nif) -> bool:
        nif = _normaliza(nif)
        return bool(nif and (self._todo.get(nif, {}).get("confirmado")
                             or _normaliza_suite(nif) in self._suite))

    def nombre_confirmado(self, nif) -> str:
        nif = _normaliza(nif)
        ficha = self._todo.get(nif, {}) if nif else {}
        if (isinstance(ficha, dict) and ficha.get("confirmado") and ficha.get("nombre")
                and not _roto(ficha["nombre"])):
            return str(ficha["nombre"]).strip()
        return self._suite.get(_normaliza_suite(nif), "")

    def buscar_por_nombre(self, nombre) -> tuple[str, str] | None:
        clave = _clave_nombre(nombre)
        if not clave:
            return None
        if self._por_nombre is None:
            self._por_nombre = _indice_por_nombre(self._todo, self._suite)
        coincidencias = self._por_nombre.get(clave)
        return next(iter(coincidencias.items())) if coincidencias and \
            len(coincidencias) == 1 else None


def _normaliza_suite(nif) -> str:
    from . import suite
    return suite._normaliza(nif)


# El índice {nombre comparable: {NIF: nombre}} de los clientes confirmados
# (aquí y en el directorio de la suite), con lo que lo decide: solo se rehace
# si cambian sus nombres o cuáles están confirmados.
_indice: dict = {"firma": None, "por_nombre": {}}


def _indice_por_nombre(todo: dict, suite_nombres: dict) -> dict:
    confirmados = [(nif, ficha.get("nombre", "")) for nif, ficha in todo.items()
                   if isinstance(ficha, dict) and ficha.get("confirmado")]
    global _indice
    firma = (tuple(confirmados), tuple(suite_nombres.items()))
    recordado = _indice
    if recordado["firma"] == firma:
        return recordado["por_nombre"]
    por_nombre: dict = {}
    for nif, nombre in confirmados:
        clave = _clave_nombre(nombre)
        if clave:
            por_nombre.setdefault(clave, {})[_normaliza(nif)] = nombre
    for nif, nombre in suite_nombres.items():
        clave = _clave_nombre(nombre) if nombre else ""
        if clave:
            por_nombre.setdefault(clave, {}).setdefault(nif, nombre)
    # De una vez (lo puede leer a la vez el hilo de la lectura).
    _indice = {"firma": firma, "por_nombre": por_nombre}
    return por_nombre


# --------------------------------------------------- regimen de recargo
# Dos clientes pueden comprar los dos con recargo de equivalencia y llevarse de
# forma distinta, porque lo que manda es SU regimen, no la factura:
#   - MINORISTA en recargo (no presenta el 303): no deduce IVA, asi que el gasto
#     se registra por el TOTAL de la factura, sin desglose.
#   - MAYORISTA en estimacion directa: SI registra el IVA y el recargo por
#     separado, con su desglose normal.
TOTAL = "total"          # minorista: un apunte por el total factura
DESGLOSE = "desglose"    # mayorista: base, IVA y recargo cada uno en lo suyo
# Actividad exenta (médicos, academias, seguros…: art. 20 de la Ley del IVA):
# no deduce el IVA de sus compras (art. 94), así que también van por el total.
# Una sociedad sí puede estar aquí.
EXENTO = "exento"
REGIMENES = (TOTAL, DESGLOSE, EXENTO)

# Ley del IVA, art. 148: el recargo de equivalencia es solo para comerciantes
# minoristas personas fisicas o entidades en atribucion de rentas (comunidades
# de bienes). Una sociedad (S.A., S.L., cooperativa, asociacion...) no puede
# estar en recargo aunque un proveedor se lo cobre. La J (sociedad civil) no
# se descarta: puede estar en atribucion de rentas.
_PERSONAS_JURIDICAS = frozenset("ABCDFGNPQRSUVW")


def puede_estar_en_recargo(nif) -> bool:
    """Si la ley permite que este cliente este en recargo de equivalencia.

    Con el NIF vacio no se descarta nada: no se sabe quien es."""
    nif = _normaliza(nif)
    if len(nif) == 11 and nif.startswith("ES"):     # NIF-IVA
        nif = nif[2:]
    return not nif or nif[0] not in _PERSONAS_JURIDICAS


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
    if guardado in REGIMENES:
        return guardado
    # Compatibilidad con la casilla de antes (era un si/no).
    if ficha.get("recargo_equivalencia"):
        return TOTAL
    return ""


def guardar_regimen_recargo(nif, regimen: str, nombre: str = "") -> None:
    nif = _normaliza(nif)
    if not nif or regimen not in REGIMENES + ("",):
        return
    todo = _leer_todo()
    ficha = todo.setdefault(nif, {})
    ficha["regimen_recargo"] = regimen
    ficha["recargo_equivalencia"] = (regimen == TOTAL)   # por si lo lee algo viejo
    if nombre:
        ficha["nombre"] = nombre
    _guardar_ficha(nif, todo[nif])
