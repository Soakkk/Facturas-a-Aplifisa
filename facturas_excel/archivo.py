"""Los PDF que va generando el escaneo: donde estan y que hacer con ellos.

Al escanear no siempre se sabe de quien son las facturas (el programa lo
averigua despues, por el NIF que se repite). Por eso un escaneo puede nacer
"sin identificar" y mudarse a la carpeta de su cliente en cuanto se sabe.

Nada se borra de verdad: lo que se quita va a una papelera dentro de la propia
carpeta de escaneos, por si acaso.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from typing import List, Optional

from . import ajustes
from .escaner import carpeta_por_defecto, nombre_libre, ruta_destino, sanear

SIN_IDENTIFICAR = "Sin identificar"
PAPELERA = "_Papelera"


def carpeta_escaneos() -> str:
    ruta = ajustes.leer("carpeta_escaneos", carpeta_por_defecto())
    os.makedirs(ruta, exist_ok=True)
    return ruta


def ruta_provisional(carpeta_base: str, tipo: str,
                     dia: Optional[date] = None) -> str:
    """Sitio para un escaneo del que aun no se sabe el cliente."""
    tipo = "ingresos" if str(tipo).lower().startswith("i") else "gastos"
    dia = dia or date.today()
    return nombre_libre(os.path.join(carpeta_base, SIN_IDENTIFICAR),
                        f"Escaneo_{tipo}_{dia:%Y-%m-%d}")


def sin_identificar(ruta: str) -> bool:
    partes = os.path.normpath(ruta).split(os.sep)
    return SIN_IDENTIFICAR in partes


def mover_a_cliente(ruta: str, cliente: str, tipo: str = "gastos",
                    dia: Optional[date] = None) -> str:
    """Muda el PDF a la carpeta del cliente con su nombre bueno.

    Devuelve la ruta nueva; si algo falla (el archivo esta abierto en otro
    programa, por ejemplo) devuelve la de antes: mover el archivo NUNCA debe
    costar el escaneo.
    """
    if not cliente or not os.path.exists(ruta):
        return ruta
    destino = ruta_destino(_base_de(ruta), cliente, tipo,
                           dia or _fecha_de_archivo(ruta))
    if os.path.normcase(destino) == os.path.normcase(ruta):
        return ruta
    try:
        shutil.move(ruta, destino)
    except OSError:
        return ruta
    _limpiar_si_vacia(os.path.dirname(ruta))
    return destino


def _base_de(ruta: str) -> str:
    """Carpeta de escaneos a la que pertenece un PDF.

    Lo normal es que este dentro de la carpeta configurada; si el usuario lo ha
    movido a otro sitio, se usa la carpeta de su carpeta (esta en la de un
    cliente).
    """
    base = carpeta_escaneos()
    ruta_abs = os.path.normcase(os.path.abspath(ruta))
    if ruta_abs.startswith(os.path.normcase(os.path.abspath(base)) + os.sep):
        return base
    return os.path.dirname(os.path.dirname(ruta))


def _fecha_de_archivo(ruta: str) -> date:
    """La fecha que lleva el propio nombre (es la del escaneo); si no la lleva,
    la del archivo. Asi renombrar o mover un PDF no le cambia la fecha."""
    encaje = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(ruta))
    if encaje:
        try:
            return date(*(int(g) for g in encaje.groups()))
        except ValueError:
            pass
    try:
        return datetime.fromtimestamp(os.path.getmtime(ruta)).date()
    except OSError:
        return date.today()


def _limpiar_si_vacia(carpeta: str) -> None:
    try:
        if os.path.isdir(carpeta) and not os.listdir(carpeta):
            os.rmdir(carpeta)
    except OSError:
        pass


@dataclass
class Escaneo:
    ruta: str
    cliente: str
    nombre: str
    fecha: date
    tamano: int          # bytes

    @property
    def tamano_texto(self) -> str:
        mb = self.tamano / (1024 * 1024)
        if mb >= 1:
            return f"{mb:.1f} MB".replace(".", ",")
        return f"{max(1, round(self.tamano / 1024))} KB"


def listar(carpeta_base: Optional[str] = None) -> List[Escaneo]:
    """Todos los PDF escaneados, del mas nuevo al mas viejo. La papelera no."""
    base = carpeta_base or carpeta_escaneos()
    encontrados: List[Escaneo] = []
    for raiz, carpetas, archivos in os.walk(base):
        carpetas[:] = [c for c in carpetas if c != PAPELERA]
        for archivo in archivos:
            if not archivo.lower().endswith(".pdf"):
                continue
            ruta = os.path.join(raiz, archivo)
            cliente = os.path.basename(raiz)
            try:
                tamano = os.path.getsize(ruta)
            except OSError:
                continue
            encontrados.append(Escaneo(
                ruta=ruta,
                cliente=cliente if os.path.normcase(raiz) != os.path.normcase(base) else "—",
                nombre=archivo,
                fecha=_fecha_de_archivo(ruta),
                tamano=tamano))
    return sorted(encontrados, key=lambda e: (e.fecha, e.nombre), reverse=True)


def a_papelera(ruta: str) -> str:
    """Quita un escaneo de en medio SIN borrarlo: se queda en _Papelera."""
    base = carpeta_escaneos()
    papelera = os.path.join(base, PAPELERA)
    os.makedirs(papelera, exist_ok=True)
    destino = os.path.join(papelera, os.path.basename(ruta))
    n = 2
    while os.path.exists(destino):
        raiz, ext = os.path.splitext(os.path.basename(ruta))
        destino = os.path.join(papelera, f"{raiz}_{n}{ext}")
        n += 1
    shutil.move(ruta, destino)
    _limpiar_si_vacia(os.path.dirname(ruta))
    return destino


def renombrar_cliente(ruta: str, cliente: str) -> str:
    """Corrige a mano de quien es un escaneo (se movio mal o se tecleo mal)."""
    return mover_a_cliente(ruta, sanear(cliente), _tipo_de_nombre(ruta))


def _tipo_de_nombre(ruta: str) -> str:
    return "ingresos" if "_ingresos_" in os.path.basename(ruta).lower() else "gastos"


def abrir(ruta: str) -> None:
    """Abre el PDF (o su carpeta) con lo que tenga puesto Windows."""
    try:
        os.startfile(ruta)  # noqa: solo Windows, que es donde corre esto
    except (OSError, AttributeError):
        pass
