"""Un solo sitio para lo que el programa recuerda: una base de datos local.

Antes cada cosa iba en su propio JSON (ajustes, clientes, proveedores, gasto
de Gemini, facturas exportadas…), cada uno con su manera de leer y escribir.
Ahora todo va en %APPDATA%\\FacturasAplifisa\\facturas_aplifisa.db, un único
archivo SQLite en el propio ordenador:

- `datos`: lo que antes eran los JSON, por colección y clave.
- `facturas`: el registro de cada factura que pasa por el programa, con su
  recorrido (leída → revisada → exportada → archivada), su Excel y su PDF.
  Ver `registro_facturas.py`.

La primera vez que se abre una colección se copia lo que hubiera en su JSON
antiguo. Los JSON antiguos NO se tocan ni se borran: quedan como estaban.

Cada escritura es una transacción: o se guarda entera o no se guarda nada.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from contextlib import closing, contextmanager
from datetime import datetime
from typing import Any, Callable, Dict, Iterator, Optional

FICHERO = "facturas_aplifisa.db"
VERSION_ESQUEMA = 1

_ESQUEMA = """
CREATE TABLE IF NOT EXISTS datos (
    coleccion   TEXT NOT NULL,
    clave       TEXT NOT NULL,
    valor       TEXT NOT NULL,
    actualizado TEXT NOT NULL,
    PRIMARY KEY (coleccion, clave)
);
CREATE TABLE IF NOT EXISTS migraciones (
    coleccion TEXT PRIMARY KEY,
    origen    TEXT,
    fecha     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facturas (
    id              TEXT PRIMARY KEY,
    cliente         TEXT NOT NULL,
    cliente_nif     TEXT,
    cliente_nombre  TEXT,
    tipo            TEXT NOT NULL,
    nif             TEXT,
    nombre          TEXT,
    num_factura     TEXT,
    fecha           TEXT,
    ejercicio       INTEGER,
    base            REAL,
    cuota_iva       REAL,
    cuota_requiv    REAL,
    cuota_irpf      REAL,
    total           REAL,
    estado          TEXT NOT NULL,
    leida_en        TEXT,
    revisada_en     TEXT,
    exportada_en    TEXT,
    archivada_en    TEXT,
    excel           TEXT,
    pdf             TEXT,
    origen          TEXT,
    paginas         TEXT,
    por_total       INTEGER,
    actualizado     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS facturas_cliente ON facturas (cliente, ejercicio);
CREATE INDEX IF NOT EXISTS facturas_nif ON facturas (nif);
"""

_preparadas: set = set()
_migradas: set = set()
_cerrojo = threading.RLock()


def ruta(carpeta: str) -> str:
    return os.path.join(carpeta, FICHERO)


def ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def conexion(carpeta: str) -> Iterator[sqlite3.Connection]:
    """Una conexión corta: se abre, se usa en una transacción y se cierra.

    Se puede usar desde cualquier hilo (el gasto de Gemini se anota desde el
    hilo que lee las facturas).
    """
    os.makedirs(carpeta, exist_ok=True)
    destino = ruta(carpeta)
    with closing(sqlite3.connect(destino, timeout=15)) as con:
        con.row_factory = sqlite3.Row
        if destino not in _preparadas:
            with _cerrojo:
                con.executescript(_ESQUEMA)
                con.execute(f"PRAGMA user_version = {VERSION_ESQUEMA}")
                try:
                    con.execute("PRAGMA journal_mode = WAL")
                except sqlite3.DatabaseError:
                    pass
                _preparadas.add(destino)
        with con:
            yield con


def _leer_json(ruta_json: str) -> Optional[dict]:
    try:
        with open(ruta_json, encoding="utf-8") as fh:
            datos = json.load(fh)
        return datos if isinstance(datos, dict) else None
    except (OSError, ValueError):
        return None


class Coleccion:
    """Un conjunto de {clave: valor} guardado en la base de datos.

    `legado` es la ruta del JSON antiguo; `convertir` (opcional) pasa su
    contenido a {clave: valor} si no tenía esa forma.
    """

    def __init__(self, nombre: str, carpeta: str, legado: str = "",
                 convertir: Optional[Callable[[dict], Dict[str, Any]]] = None):
        self.nombre = nombre
        self.carpeta = carpeta
        self.legado = legado
        self.convertir = convertir

    # ------------------------------------------------------------ migrar
    def _migrar(self, con: sqlite3.Connection) -> None:
        marca = (ruta(self.carpeta), self.nombre)
        if marca in _migradas:
            return
        hecho = con.execute("SELECT 1 FROM migraciones WHERE coleccion = ?",
                            (self.nombre,)).fetchone()
        if hecho:
            _migradas.add(marca)
            return
        antiguos = _leer_json(self.legado) if self.legado else None
        if antiguos and self.convertir:
            try:
                antiguos = self.convertir(antiguos)
            except Exception:
                antiguos = None       # un JSON con forma rara no se copia
        if not isinstance(antiguos, dict):
            antiguos = None
        if antiguos:
            momento = ahora()
            con.executemany(
                "INSERT OR IGNORE INTO datos VALUES (?, ?, ?, ?)",
                [(self.nombre, str(k), json.dumps(v, ensure_ascii=False), momento)
                 for k, v in antiguos.items()])
        con.execute("INSERT OR REPLACE INTO migraciones VALUES (?, ?, ?)",
                    (self.nombre, self.legado if antiguos else None, ahora()))
        con.commit()
        _migradas.add(marca)

    @contextmanager
    def _con(self) -> Iterator[sqlite3.Connection]:
        with conexion(self.carpeta) as con:
            self._migrar(con)
            yield con

    # ------------------------------------------------------------- leer
    def leer_todo(self) -> Dict[str, Any]:
        try:
            with self._con() as con:
                filas = con.execute(
                    "SELECT clave, valor FROM datos WHERE coleccion = ?",
                    (self.nombre,)).fetchall()
        except sqlite3.Error:
            return {}
        salida = {}
        for fila in filas:
            try:
                salida[fila["clave"]] = json.loads(fila["valor"])
            except ValueError:
                continue
        return salida

    def leer(self, clave: str, por_defecto: Any = None) -> Any:
        try:
            with self._con() as con:
                fila = con.execute(
                    "SELECT valor FROM datos WHERE coleccion = ? AND clave = ?",
                    (self.nombre, str(clave))).fetchone()
        except sqlite3.Error:
            return por_defecto
        if not fila:
            return por_defecto
        try:
            return json.loads(fila["valor"])
        except ValueError:
            return por_defecto

    # ---------------------------------------------------------- escribir
    def guardar(self, clave: str, valor: Any) -> bool:
        return self.guardar_varios({clave: valor})

    def guardar_varios(self, valores: Dict[str, Any]) -> bool:
        try:
            with self._con() as con:
                momento = ahora()
                con.executemany(
                    "INSERT OR REPLACE INTO datos VALUES (?, ?, ?, ?)",
                    [(self.nombre, str(k), json.dumps(v, ensure_ascii=False), momento)
                     for k, v in valores.items()])
            return True
        except (sqlite3.Error, TypeError, ValueError):
            return False

    def modificar(self, clave: str, cambio: Callable[[Any], Any],
                  por_defecto: Any = None) -> Any:
        """Lee, cambia y guarda un valor en la misma transacción.

        Así dos hilos que apuntan a la vez (el gasto de dos hojas) no se
        pisan: el segundo espera a que termine el primero.
        """
        with self._con():
            pass                      # la copia del JSON antiguo, antes
        with conexion(self.carpeta) as con:
            con.execute("BEGIN IMMEDIATE")
            fila = con.execute(
                "SELECT valor FROM datos WHERE coleccion = ? AND clave = ?",
                (self.nombre, str(clave))).fetchone()
            actual = json.loads(fila["valor"]) if fila else por_defecto
            nuevo = cambio(actual)
            con.execute("INSERT OR REPLACE INTO datos VALUES (?, ?, ?, ?)",
                        (self.nombre, str(clave),
                         json.dumps(nuevo, ensure_ascii=False), ahora()))
            return nuevo

    def borrar(self, clave: str) -> bool:
        try:
            with self._con() as con:
                cursor = con.execute(
                    "DELETE FROM datos WHERE coleccion = ? AND clave = ?",
                    (self.nombre, str(clave)))
            return cursor.rowcount > 0
        except sqlite3.Error:
            return False
