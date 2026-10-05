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

Se guardan las 15 últimas de cada ordenador (la carpeta puede estar
compartida), y nunca se borra la que más facturas tiene: si el registro se
queda vacío o se estropea, sus copias no pueden llevarse la última buena. Al
abrir con el registro vacío y una copia con facturas, se ofrece restaurarla.

Restaurar hace antes una copia de lo de ahora, devuelve el registro (también
si la base en uso está dañada) y no cambia la carpeta de documentación. Las
notas y el índice solo vuelven si faltan o están dañados.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
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
    equipo: str = ""

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


def equipo() -> str:
    """Este ordenador: la carpeta de copias puede estar compartida (OneDrive)."""
    return (os.environ.get("COMPUTERNAME") or socket.gethostname() or "").upper()


def _solo_lectura(db: str):
    return sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True,
                           timeout=15)


def _contar_facturas(db: str) -> Optional[int]:
    """Cuántas facturas tiene el registro de esa base (None si no se puede
    leer). En solo lectura: nunca crea una base vacía donde no la había."""
    try:
        if not os.path.isfile(db) or not os.path.getsize(db):
            return None
        with closing(_solo_lectura(db)) as con:
            return con.execute("SELECT COUNT(*) FROM facturas").fetchone()[0]
    except sqlite3.Error:
        return None


def _base_sana(db: str) -> bool:
    """Se abre, pasa la comprobación de SQLite y tiene el registro."""
    try:
        if not os.path.isfile(db) or not os.path.getsize(db):
            return False
        with closing(_solo_lectura(db)) as con:
            if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                return False
            return con.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND "
                "name = 'facturas'").fetchone() is not None
    except sqlite3.Error:
        return False


def _copiar_base(origen: str, destino: str) -> bool:
    """SQLite copia la base entera y coherente, también con su diario (WAL).
    Si está dañada, se guarda tal cual (con su diario) para poder rescatarla.
    Devuelve si es una copia buena."""
    try:
        with closing(sqlite3.connect(origen, timeout=15)) as fuente, \
                closing(sqlite3.connect(destino)) as copia:
            fuente.backup(copia)
        return True
    except sqlite3.Error:
        for extra in ("", "-wal", "-shm"):
            if os.path.exists(origen + extra):
                shutil.copy2(origen + extra, destino + extra)
        return False


def hacer(motivo: str = "diaria", rotar_despues: bool = True) -> str:
    """Hace una copia ahora y devuelve su carpeta. Si algo falla, no deja
    una copia a medias."""
    momento = datetime.now()
    nombre = f"{momento:%Y-%m-%d_%H%M%S}"
    raiz = carpeta()
    destino = os.path.join(raiz, nombre)
    n = 2
    while os.path.exists(destino):
        destino = os.path.join(raiz, f"{nombre}-{n}")
        n += 1
    os.makedirs(destino)
    try:
        contenido, buena = [], None
        db = _base_de_datos()
        if os.path.exists(db):
            buena = _copiar_base(db, os.path.join(destino, almacen.FICHERO))
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
                       "equipo": equipo(), "contenido": contenido,
                       "base_danada": buena is False,
                       "facturas": _contar_facturas(
                           os.path.join(destino, almacen.FICHERO))},
                      fh, ensure_ascii=False, indent=2)
    except BaseException:
        shutil.rmtree(destino, ignore_errors=True)
        raise
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
            tamano = sum(os.path.getsize(os.path.join(ruta, f))
                         for f in os.listdir(ruta)
                         if os.path.isfile(os.path.join(ruta, f)))
        except (OSError, ValueError, KeyError, TypeError):
            continue
        copias.append(Copia(ruta, fecha, str(resumen.get("motivo") or ""),
                            tamano, resumen.get("facturas"),
                            str(resumen.get("equipo") or "")))
    return sorted(copias, key=lambda c: c.fecha, reverse=True)


def _mias(copias: List[Copia]) -> List[Copia]:
    yo = equipo()
    return [c for c in copias if not c.equipo or c.equipo == yo]


def rotar(guardar: int = GUARDAR) -> None:
    """Se quedan las últimas de este ordenador (las de otro las rota el
    otro). La más completa (la que más facturas tiene) no se borra nunca:
    con un registro vacío o estropeado, quince días de copias de ese
    registro no pueden llevarse la última buena."""
    mias = _mias(listar())
    if len(mias) <= guardar:
        return
    completa = max(mias, key=lambda c: (c.facturas or 0, c.fecha))
    for vieja in mias[guardar:]:
        if vieja.ruta != completa.ruta:
            shutil.rmtree(vieja.ruta, ignore_errors=True)


def hecha_hoy(hoy: Optional[date] = None) -> bool:
    hoy = hoy or date.today()
    return any(c.fecha.date() == hoy for c in _mias(listar()))


def diaria() -> str:
    """La copia del día, si aún no se ha hecho. Devuelve su carpeta o ""."""
    if hecha_hoy():
        return ""
    return hacer("diaria")


def mejor_que_la_actual() -> Optional[Copia]:
    """Si el registro de este ordenador está vacío (o no se puede leer) y hay
    una copia con facturas, esa copia (la más nueva): ha cambiado de
    ordenador o se ha estropeado, y hay que ofrecer restaurarla."""
    if _contar_facturas(_base_de_datos()):
        return None
    return next((c for c in listar() if (c.facturas or 0) > 0), None)


@dataclass
class Restauracion:
    antes: str                      # la copia de lo que había antes
    avisos: List[str] = field(default_factory=list)


def restaurar(ruta_copia: str) -> Restauracion:
    """Vuelve al registro de esa copia (facturas, clientes, proveedores,
    cuentas y ajustes). La carpeta de documentación no cambia.

    Antes copia lo de ahora («antes de restaurar»). Las notas y el índice de
    carpetas solo vuelven si aquí faltan o están dañados: si no, se perdería
    lo apuntado y los clientes dados de alta después de la copia. El
    programa debe volver a abrirse."""
    from . import ajustes
    db_copia = os.path.join(ruta_copia, almacen.FICHERO)
    if not _base_sana(db_copia):
        raise ValueError("Esa copia no tiene un registro del programa que se "
                         "pueda usar.")
    # Lo que tiene que quedar como está, leído antes de cambiar la base: la
    # carpeta de documentación (es un ajuste, y va en la base) y lo que
    # cuelga de ella.
    from .archivo import carpeta_escaneos
    carpeta_doc = carpeta_escaneos()
    ruta_indice, ruta_notas = _ruta_indice(), _ruta_notas()
    # Sin quitar copias viejas todavía: podría irse la que se restaura.
    antes = hacer("antes de restaurar", rotar_despues=False)
    db = _base_de_datos()
    if _base_sana(db):
        # Encima de la base en uso, sin cambiar el fichero: así no se mezcla
        # con su diario (WAL).
        with closing(_solo_lectura(db_copia)) as fuente, \
                closing(sqlite3.connect(db, timeout=15)) as actual:
            fuente.backup(actual)
    else:
        # Dañada: se sustituye el fichero entero, sin su diario viejo.
        temporal = db + ".restaurando"
        shutil.copy2(db_copia, temporal)
        for extra in ("-wal", "-shm"):
            try:
                os.remove(db + extra)
            except FileNotFoundError:
                pass
        os.replace(temporal, db)
    if ajustes.leer("carpeta_escaneos", None) != carpeta_doc:
        ajustes.guardar("carpeta_escaneos", carpeta_doc)
    resultado = Restauracion(antes)
    for como, ruta, sano in ((NOTAS, ruta_notas, _notas_sanas),
                             (INDICE, ruta_indice, _indice_sano)):
        origen = os.path.join(ruta_copia, como)
        if not os.path.exists(origen) or sano(ruta):
            continue
        temporal = ruta + ".restaurando"
        try:
            shutil.copy2(origen, temporal)
            os.replace(temporal, ruta)
        except OSError as error:
            resultado.avisos.append(f"No se pudo recuperar {como} ({error}).")
        finally:
            if os.path.exists(temporal):
                try:
                    os.remove(temporal)
                except OSError:
                    pass
    rotar()
    return resultado


def _notas_sanas(ruta: str) -> bool:
    try:
        with open(ruta, encoding="utf-8") as fh:
            return bool(fh.read().strip())
    except (OSError, ValueError):
        return False


def _indice_sano(ruta: str) -> bool:
    from .identidad_archivo import leer
    if not os.path.exists(ruta):
        return False
    try:
        leer(os.path.dirname(ruta))
        return True
    except (OSError, ValueError):
        return False
