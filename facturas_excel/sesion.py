"""Persistencia local del lote en curso entre aperturas del programa.

El lote se guarda solo mientras se trabaja (no únicamente al cerrar): un
apagón o un cuelgue no puede llevarse la revisión ni lecturas ya pagadas. Y
una sesión que no se puede abrir (dañada, de otra versión) no se borra nunca:
se aparta con la fecha para poder recuperarla.
"""

from __future__ import annotations

import glob
import gzip
import hashlib
import os
import pickle
import shutil
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
# El guardado automático va en un solo hilo escritor, con como mucho una
# foto esperando: si llegan varias mientras escribe, solo cuenta la última
# (las de en medio ya son viejas). Antes cada guardado lanzaba su hilo con
# su propia copia del lote. Y lo que no ha cambiado no se vuelve a escribir.
_cerrojo_pendiente = threading.Lock()
_pendiente: tuple | None = None    # (paquete, número, huella) sin escribir
_escribiendo = False               # el hilo escritor está en marcha
_huella_pedida = None              # la de la última foto pedida…
_numero_pedido = 0                 # …y su número
_huella_escrita = None             # la de lo que hay en el disco
_apartada = ""
# Una sesión que no se pudo abrir NI apartar (bloqueada por el antivirus u
# otra copia del programa): en esta ejecución no se borra ni se pisa.
_intocable = ""


def _ruta() -> str:
    return os.path.join(dir_datos(), FICHERO)


def _empaquetar(datos: dict) -> bytes:
    return pickle.dumps({"version": VERSION, "datos": datos},
                        protocol=pickle.HIGHEST_PROTOCOL)


def _huella(paquete: bytes) -> bytes:
    """Lo que identifica una foto del lote, y dónde va (otra carpeta de
    datos es otra sesión)."""
    resumen = hashlib.sha256(os.path.normcase(_ruta()).encode("utf-8"))
    resumen.update(paquete)
    return resumen.digest()


def _olvidar_huellas() -> None:
    """Lo del disco ya no es lo último escrito (se borró o se apartó).
    Se llama con el cerrojo del fichero cogido."""
    global _huella_pedida, _huella_escrita
    with _cerrojo_pendiente:
        _huella_pedida = _huella_escrita = None


def _siguiente() -> int:
    global _pedidas
    with _cerrojo_numeros:
        _pedidas += 1
        return _pedidas


def _escribir(paquete: bytes, numero: int) -> None:
    """Escribe de forma atómica, si no hay ya algo más nuevo escrito."""
    global _escrita, _huella_escrita
    with _cerrojo_fichero:
        if numero <= _escrita:
            return
        ruta = _ruta()
        if _intocable and os.path.normcase(ruta) == os.path.normcase(_intocable):
            raise OSError("el lote de la última vez no se pudo abrir ni "
                          "apartar, y no se pisa")
        temporal = ruta + ".tmp"
        try:
            with open(temporal, "wb") as crudo:
                with gzip.GzipFile(fileobj=crudo, mode="wb", compresslevel=3) as fh:
                    fh.write(paquete)
                # En el disco de verdad antes de sustituir al anterior: tras
                # un corte de luz, el nuevo entero o el de antes, no a medias.
                crudo.flush()
                os.fsync(crudo.fileno())
            os.replace(temporal, ruta)
            _escrita = numero
            _huella_escrita = _huella(paquete)
        except Exception:
            try:
                if os.path.exists(temporal):
                    os.remove(temporal)
            except OSError:
                pass
            raise


def guardar(datos: dict) -> None:
    """Escribe la sesión completa de forma atómica (y espera a que acabe).

    Si en el disco ya está exactamente esto (lo dejó el guardado automático
    y no se ha tocado nada), no se reescribe: así se cierra al momento."""
    global _ultimo_error
    paquete = _empaquetar(datos)
    huella = _huella(paquete)
    with _cerrojo_pendiente:
        if (huella == _huella_escrita and _pendiente is None and not _escribiendo
                and os.path.exists(_ruta())):
            _ultimo_error = ""
            return
    numero = _siguiente()
    _escribir(paquete, numero)
    _pedida(huella, numero)
    _ultimo_error = ""


def _pedida(huella: bytes, numero: int) -> None:
    """Apunta la última foto pedida (si no hay ya una más nueva)."""
    global _huella_pedida, _numero_pedido
    with _cerrojo_pendiente:
        if numero > _numero_pedido:
            _huella_pedida, _numero_pedido = huella, numero


def guardar_en_segundo_plano(datos: dict) -> int:
    """Guardado automático: la foto del lote se toma ahora (en este hilo) y
    se comprime y escribe aparte, para no parar la pantalla.

    Devuelve el número de la foto que lleva esto, para saber cuándo está en
    el disco (ver `escrita`)."""
    global _pendiente, _escribiendo, _huella_pedida, _numero_pedido
    paquete = _empaquetar(datos)
    huella = _huella(paquete)
    with _cerrojo_pendiente:
        if huella == _huella_pedida and (_pendiente is not None or _escribiendo
                                         or os.path.exists(_ruta())):
            return _numero_pedido   # nada ha cambiado desde la última foto
        numero = _siguiente()
        _huella_pedida, _numero_pedido = huella, numero
        _pendiente = (paquete, numero, huella)
        if _escribiendo:
            return numero   # el hilo que escribe la recoge al acabar
        _escribiendo = True
        hilo = threading.Thread(target=_escritor, name="guardar-sesion", daemon=True)
        _hilos[:] = [h for h in _hilos if h.is_alive()] + [hilo]
    hilo.start()
    return numero


def escrita(numero: int) -> bool:
    """Si la foto `numero` (o una más nueva, o el borrado) ya está en el disco."""
    return _escrita >= numero


def proxima() -> int:
    """El número que llevará la próxima foto que se pida."""
    with _cerrojo_numeros:
        return _pedidas + 1


def _escritor() -> None:
    """Escribe la última foto pedida, y la siguiente si llega mientras."""
    global _pendiente, _escribiendo, _huella_pedida, _ultimo_error
    while True:
        with _cerrojo_pendiente:
            if _pendiente is None:
                _escribiendo = False
                return
            paquete, numero, huella = _pendiente
            _pendiente = None
        try:
            _escribir(paquete, numero)
            _ultimo_error = ""
        except Exception as error:   # lo avisa la ventana
            _ultimo_error = str(error) or type(error).__name__
            with _cerrojo_pendiente:
                if _huella_pedida == huella:
                    _huella_pedida = None   # el próximo vuelve a intentarlo


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
    global _intocable
    with _cerrojo_fichero:
        _olvidar_huellas()
        if not os.path.exists(ruta):
            return ""
        try:
            os.replace(ruta, destino)
        except OSError:
            # Bloqueada: al menos una copia; y si ni eso, no se toca.
            try:
                shutil.copy2(ruta, destino)
            except OSError:
                _intocable = ruta
                return ""
    _apartada = destino
    viejas = sorted(glob.glob(os.path.join(carpeta, APARTADAS + "*")))
    for vieja in viejas[:-MAX_APARTADAS]:
        try:
            os.remove(vieja)
        except OSError:
            pass
    return destino


def intocable() -> str:
    """La sesión que no se pudo abrir ni apartar ("" si ninguna)."""
    return _intocable


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
        _olvidar_huellas()
        ruta = _ruta()
        if _intocable and os.path.normcase(ruta) == os.path.normcase(_intocable):
            return
        try:
            os.remove(ruta)
        except OSError:
            pass
