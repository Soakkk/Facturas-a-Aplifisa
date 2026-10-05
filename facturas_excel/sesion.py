"""Persistencia local del lote en curso entre aperturas del programa.

El lote se guarda solo mientras se trabaja (no únicamente al cerrar): un
apagón o un cuelgue no puede llevarse la revisión ni lecturas ya pagadas. Y
una sesión que no se puede abrir (dañada, de otra versión) no se borra nunca:
se aparta con la fecha para poder recuperarla.
"""

from __future__ import annotations

import glob
import gzip
import os
import pickle
import threading
from datetime import datetime

from .rutas import dir_datos

VERSION = 1
FICHERO = "sesion_lote.pkl.gz"
APARTADAS = "sesion_lote.no-recuperada-"
MAX_APARTADAS = 5

# Las escrituras en segundo plano van en orden: una copia vieja que termine
# tarde nunca pisa a una más nueva (ni resucita la sesión tras borrarla).
_cerrojo_numeros = threading.Lock()
_cerrojo_fichero = threading.Lock()
_pedidas = 0       # número de la última escritura pedida
_escrita = 0       # número de la última escrita (o anulada al borrar)
_hilos: list[threading.Thread] = []
_ultimo_error = ""
_apartada = ""


def _ruta() -> str:
    return os.path.join(dir_datos(), FICHERO)


def _empaquetar(datos: dict) -> bytes:
    return pickle.dumps({"version": VERSION, "datos": datos},
                        protocol=pickle.HIGHEST_PROTOCOL)


def _siguiente() -> int:
    global _pedidas
    with _cerrojo_numeros:
        _pedidas += 1
        return _pedidas


def _escribir(paquete: bytes, numero: int) -> None:
    """Escribe de forma atómica, si no hay ya algo más nuevo escrito."""
    global _escrita
    with _cerrojo_fichero:
        if numero <= _escrita:
            return
        ruta = _ruta()
        temporal = ruta + ".tmp"
        try:
            with gzip.open(temporal, "wb", compresslevel=3) as fh:
                fh.write(paquete)
            os.replace(temporal, ruta)
            _escrita = numero
        except Exception:
            try:
                if os.path.exists(temporal):
                    os.remove(temporal)
            except OSError:
                pass
            raise


def guardar(datos: dict) -> None:
    """Escribe la sesión completa de forma atómica (y espera a que acabe)."""
    global _ultimo_error
    paquete = _empaquetar(datos)
    _escribir(paquete, _siguiente())
    _ultimo_error = ""


def guardar_en_segundo_plano(datos: dict) -> None:
    """Guardado automático: la foto del lote se toma ahora (en este hilo) y
    se comprime y escribe aparte, para no parar la pantalla."""
    paquete = _empaquetar(datos)
    numero = _siguiente()

    def escribir():
        global _ultimo_error
        try:
            _escribir(paquete, numero)
            _ultimo_error = ""
        except Exception as error:   # lo avisa la ventana
            _ultimo_error = str(error) or type(error).__name__

    hilo = threading.Thread(target=escribir, name="guardar-sesion", daemon=True)
    _hilos[:] = [h for h in _hilos if h.is_alive()] + [hilo]
    hilo.start()


def ultimo_error() -> str:
    """El fallo del último guardado automático ("" si fue bien)."""
    return _ultimo_error


def esperar(segundos: float = 30.0) -> None:
    """Espera a que terminen los guardados en segundo plano."""
    for hilo in list(_hilos):
        hilo.join(segundos)
    _hilos[:] = [h for h in _hilos if h.is_alive()]


def cargar() -> dict | None:
    """Devuelve la sesión guardada, o None si no hay.

    Si hay una pero no se puede abrir (dañada, de otra versión), se aparta
    con la fecha en vez de perderla: ver `apartar`."""
    esperar()
    ruta = _ruta()
    if not os.path.exists(ruta):
        return None
    try:
        with gzip.open(ruta, "rb") as fh:
            paquete = pickle.load(fh)
        if isinstance(paquete, dict) and paquete.get("version") == VERSION \
                and isinstance(paquete.get("datos"), dict):
            return paquete["datos"]
    except Exception:
        pass
    apartar()
    return None


def apartar() -> str:
    """Deja la sesión que no se pudo abrir como
    `sesion_lote.no-recuperada-FECHA.pkl.gz` y devuelve su ruta ("" si no
    había). Se quedan las cinco últimas."""
    global _apartada
    esperar()
    ruta = _ruta()
    carpeta = os.path.dirname(ruta)
    base = os.path.join(carpeta, f"{APARTADAS}{datetime.now():%Y%m%d-%H%M%S}")
    destino, n = base + ".pkl.gz", 1
    while os.path.exists(destino):
        n += 1
        destino = f"{base}-{n}.pkl.gz"
    with _cerrojo_fichero:
        if not os.path.exists(ruta):
            return ""
        try:
            os.replace(ruta, destino)
        except OSError:
            return ""
    _apartada = destino
    viejas = sorted(glob.glob(os.path.join(carpeta, APARTADAS + "*")))
    for vieja in viejas[:-MAX_APARTADAS]:
        try:
            os.remove(vieja)
        except OSError:
            pass
    return destino


def apartada() -> str:
    """La última sesión apartada en esta ejecución ("" si ninguna)."""
    return _apartada


def borrar() -> None:
    """Borra la sesión (lote vacío) y anula los guardados pendientes."""
    global _escrita
    with _cerrojo_numeros:
        hasta = _pedidas
    with _cerrojo_fichero:
        _escrita = max(_escrita, hasta)
        try:
            os.remove(_ruta())
        except OSError:
            pass
