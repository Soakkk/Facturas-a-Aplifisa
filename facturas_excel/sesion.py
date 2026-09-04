"""Persistencia local del lote en curso entre aperturas del programa."""

from __future__ import annotations

import gzip
import os
import pickle

from .rutas import dir_datos

VERSION = 1
FICHERO = "sesion_lote.pkl.gz"


def _ruta() -> str:
    return os.path.join(dir_datos(), FICHERO)


def guardar(datos: dict) -> None:
    """Escribe la sesión completa de forma atómica."""
    ruta = _ruta()
    temporal = ruta + ".tmp"
    paquete = {"version": VERSION, "datos": datos}
    try:
        with gzip.open(temporal, "wb", compresslevel=3) as fh:
            pickle.dump(paquete, fh, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(temporal, ruta)
    except Exception:
        try:
            if os.path.exists(temporal):
                os.remove(temporal)
        except OSError:
            pass
        raise


def cargar() -> dict | None:
    """Devuelve la sesión si existe y es de una versión compatible."""
    try:
        with gzip.open(_ruta(), "rb") as fh:
            paquete = pickle.load(fh)
        if not isinstance(paquete, dict) or paquete.get("version") != VERSION:
            return None
        datos = paquete.get("datos")
        return datos if isinstance(datos, dict) else None
    except Exception:
        return None


def borrar() -> None:
    try:
        os.remove(_ruta())
    except OSError:
        pass
