"""Copias de seguridad de lo que el programa recuerda.

Hasta la 1.23 no había ninguna: un disco roto, un cambio de ordenador o un
fichero estropeado se llevaban el registro de facturas (qué se exportó y
dónde está su PDF), los clientes, los proveedores y las notas.

Una vez al día (al abrir el programa), y antes de instalar una actualización,
se copia en «Documentación Facturas/_Copias de seguridad/FECHA»:

- la base de datos (`facturas_aplifisa.db`), con la copia de SQLite, que la
  deja entera y al día aunque el programa esté escribiendo en ella;
- las notas para Claude;
- el índice de carpetas de clientes del archivo (`.clientes.json`);
- el directorio de clientes compartido con la suite (solo copia: no se
  restaura, porque lo escriben también los otros programas).

Se guardan las últimas 15. Restaurar hace antes una copia de lo de ahora.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from . import almacen
from .rutas import dir_datos

CARPETA = "_Copias de seguridad"
GUARDAR = 15
RESUMEN = "copia.json"
NOTAS = "notas-para-claude.md"
INDICE = "indice_carpetas.json"
SUITE = "suite_clientes.json"


@dataclass
class Copia:
    ruta: str
    fecha: datetime
    motivo: str
    tamano: int
    facturas: Optional[int]

    @property
    def tamano_legible(self) -> str:
        mb = self.tamano / (1024 * 1024)
        if mb >= 1:
            return f"{mb:.1f} MB".replace(".", ",")
        return f"{max(1, round(self.tamano / 1024))} KB"


def carpeta() -> str:
    """Dentro del archivo de documentación (que es lo que se guarda y se
    lleva de un ordenador a otro). Si no se puede, en los datos del programa."""
    try:
        from .archivo import carpeta_escaneos
        destino = os.path.join(carpeta_escaneos(), CARPETA)
        os.makedirs(destino, exist_ok=True)
        return destino
    except OSError:
        destino = os.path.join(dir_datos(), CARPETA)
        os.makedirs(destino, exist_ok=True)
        return destino


def _base_de_datos() -> str:
    return almacen.ruta(dir_datos())


def _ruta_indice() -> str:
    from .archivo import carpeta_escaneos
    from .identidad_archivo import INDICE as FICHERO_INDICE
    return os.path.join(carpeta_escaneos(), FICHERO_INDICE)


def _ruta_notas() -> str:
    from .pendientes import ruta_notas
    return ruta_notas()


def _ruta_suite() -> str:
    from .suite import ruta_directorio
    return ruta_directorio()


def _copiar_base(origen: str, destino: str) -> None:
    """SQLite copia la base entera y coherente, también con su diario (WAL)."""
    with closing(sqlite3.connect(origen, timeout=15)) as fuente, \
            closing(sqlite3.connect(destino)) as copia:
        fuente.backup(copia)


def _contar_facturas(db: str) -> Optional[int]:
    try:
        with closing(sqlite3.connect(db)) as con:
            return con.execute("SELECT COUNT(*) FROM facturas").fetchone()[0]
    except sqlite3.Error:
        return None


def hacer(motivo: str = "diaria", rotar_despues: bool = True) -> str:
    """Hace una copia ahora y devuelve su carpeta."""
    momento = datetime.now()
    nombre = f"{momento:%Y-%m-%d_%H%M%S}"
    destino = os.path.join(carpeta(), nombre)
    n = 2
    while os.path.exists(destino):
        destino = os.path.join(carpeta(), f"{nombre}-{n}")
        n += 1
    os.makedirs(destino)
    contenido = []
    db = _base_de_datos()
    if os.path.exists(db):
        _copiar_base(db, os.path.join(destino, almacen.FICHERO))
        contenido.append(almacen.FICHERO)
    for origen, como in ((_ruta_notas, NOTAS), (_ruta_indice, INDICE),
                         (_ruta_suite, SUITE)):
        try:
            ruta = origen()
            if os.path.exists(ruta):
                shutil.copy2(ruta, os.path.join(destino, como))
                contenido.append(como)
        except OSError:
            continue
    from . import __version__
    with open(os.path.join(destino, RESUMEN), "w", encoding="utf-8") as fh:
        json.dump({"fecha": momento.isoformat(timespec="seconds"),
                   "motivo": motivo, "version": __version__,
                   "contenido": contenido,
                   "facturas": _contar_facturas(
                       os.path.join(destino, almacen.FICHERO))},
                  fh, ensure_ascii=False, indent=2)
    if rotar_despues:
        rotar()
    return destino


def listar() -> List[Copia]:
    """Las copias que hay, de la más nueva a la más vieja."""
    try:
        raiz = carpeta()
        nombres = os.listdir(raiz)
    except OSError:
        return []
    copias = []
    for nombre in nombres:
        ruta = os.path.join(raiz, nombre)
        try:
            with open(os.path.join(ruta, RESUMEN), encoding="utf-8") as fh:
                resumen = json.load(fh)
            fecha = datetime.fromisoformat(resumen["fecha"])
        except (OSError, ValueError, KeyError, TypeError):
            continue
        tamano = sum(os.path.getsize(os.path.join(ruta, f))
                     for f in os.listdir(ruta)
                     if os.path.isfile(os.path.join(ruta, f)))
        copias.append(Copia(ruta, fecha, str(resumen.get("motivo") or ""),
                            tamano, resumen.get("facturas")))
    return sorted(copias, key=lambda c: c.fecha, reverse=True)


def rotar(guardar: int = GUARDAR) -> None:
    for vieja in listar()[guardar:]:
        shutil.rmtree(vieja.ruta, ignore_errors=True)


def hecha_hoy(hoy: Optional[date] = None) -> bool:
    hoy = hoy or date.today()
    return any(c.fecha.date() == hoy for c in listar())


def diaria() -> str:
    """La copia del día, si aún no se ha hecho. Devuelve su carpeta o ""."""
    if hecha_hoy():
        return ""
    return hacer("diaria")


def restaurar(ruta_copia: str) -> str:
    """Vuelve a lo que había en esa copia (base de datos, notas e índice).

    Antes copia lo de ahora («antes de restaurar»), por si hay que volver
    atrás, y devuelve esa carpeta. El programa debe volver a abrirse."""
    db_copia = os.path.join(ruta_copia, almacen.FICHERO)
    if not os.path.exists(db_copia):
        raise ValueError("Esa copia no tiene la base de datos del programa.")
    # Sin quitar copias viejas todavía: podría irse la que se restaura.
    antes = hacer("antes de restaurar", rotar_despues=False)
    db = _base_de_datos()
    # La copia vuelve encima de la base en uso (no se cambia el fichero:
    # así no se mezcla con su diario WAL).
    with closing(sqlite3.connect(db_copia)) as fuente, \
            closing(sqlite3.connect(db, timeout=15)) as actual:
        fuente.backup(actual)
    for como, destino in ((NOTAS, _ruta_notas), (INDICE, _ruta_indice)):
        origen = os.path.join(ruta_copia, como)
        if os.path.exists(origen):
            ruta = destino()
            temporal = ruta + ".restaurando"
            shutil.copy2(origen, temporal)
            os.replace(temporal, ruta)
    rotar()
    return antes
